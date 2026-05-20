"""Local research run orchestration."""

from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
import re
from typing import Any

import pandas as pd

from aurora.backtesting.engine import BacktestConfig, BacktestResult, SimpleLongOnlyBacktester
from aurora.backtesting.exceptions import AuroraBacktestError
from aurora.backtesting.metrics import metrics_to_dict
from aurora.data.base import MarketDataRequest
from aurora.data.cache import cache_key, load_market_data, save_market_data
from aurora.data.exceptions import AuroraDataError
from aurora.data.normalize import STANDARD_OHLCV_COLUMNS
from aurora.data.yfinance_source import YFinanceDataSource
from aurora.features.build_features import build_features
from aurora.reporting.reports import save_json_report, save_markdown_report
from aurora.strategies.exceptions import (
    SignalGenerationError,
    StrategyConfigError,
    StrategyRegistryError,
)
from aurora.strategies.registry import instantiate_strategy, load_strategy_from_registry
from aurora.validation.overfitting import diagnose_backtest_overfitting
from aurora.validation.report import overfitting_report_to_dict
from aurora.validation.leakage_monitor import (
    check_leakage_for_run,
    load_leakage_report,
    LeakageError,
)

DATA_MODE_CACHE_ONLY = "cache_only"
DATA_MODE_DOWNLOAD_IF_MISSING = "download_if_missing"
SUPPORTED_DATA_MODES = {DATA_MODE_CACHE_ONLY, DATA_MODE_DOWNLOAD_IF_MISSING}
RESEARCH_RUN_SAFETY_FLAGS = {
    "research_only": True,
    "placed_orders": False,
    "used_broker": False,
    "wrote_ledger": False,
    "external_llm_calls": False,
}


@dataclass(frozen=True)
class ResearchRunConfig:
    """Configuration for a local research-only run."""

    strategy_id: str
    run_id: str | None = None
    symbols: list[str] | None = None
    start_date: str | None = None
    end_date: str | None = None
    data_mode: str = DATA_MODE_CACHE_ONLY
    data_dir: str = "data"
    strategies_dir: str = "data/strategies"
    output_dir: str = "data/research_runs"
    initial_cash: float = 100000.0
    commission_bps: float = 1.0
    slippage_bps: float = 5.0
    max_position_pct: float | None = None
    build_features: bool = True
    write_report: bool = True
    skip_leakage_check: bool = False


@dataclass(frozen=True)
class ResearchRunResult:
    """Summary of a completed local research run."""

    run_id: str
    strategy_id: str
    symbols: list[str]
    started_at: str
    completed_at: str
    output_dir: str
    config_path: str
    signals_path: str | None
    backtest_path: str | None
    diagnostics_path: str | None
    manifest_path: str | None
    report_path: str | None
    metrics: dict[str, Any]
    diagnostics: dict[str, Any]
    warnings: list[str]


class ResearchRunError(Exception):
    """Raised when a local research run cannot complete."""


def generate_research_run_id(strategy_id: str, timestamp: datetime | None = None) -> str:
    """Generate a filesystem-safe research run identifier."""
    resolved_timestamp = timestamp or datetime.now(UTC)
    if resolved_timestamp.tzinfo is None:
        resolved_timestamp = resolved_timestamp.replace(tzinfo=UTC)
    stamp = resolved_timestamp.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    strategy_slug = _slugify(strategy_id) or "strategy"
    return f"{stamp}_{strategy_slug}"


def research_run_config_to_dict(config: ResearchRunConfig) -> dict[str, Any]:
    """Convert a research run config to a JSON-serializable dictionary."""
    return asdict(config)


def research_run_result_to_dict(result: ResearchRunResult) -> dict[str, Any]:
    """Convert a research run result to a JSON-serializable dictionary."""
    return asdict(result)


def run_research_cycle(config: ResearchRunConfig) -> ResearchRunResult:
    """Run a local research-only strategy cycle and write auditable artifacts."""
    _validate_config(config)
    started_at = datetime.now(UTC).isoformat()
    run_id, run_dir = _create_run_dir(config)
    resolved_config = replace(config, run_id=run_id)
    config_path = save_json_report(
        research_run_config_to_dict(resolved_config),
        run_dir / "config.json",
    )
    warnings: list[str] = []
    market_data_path = run_dir / "market_data.csv"
    features_path: Path | None = None
    manifest_path = run_dir / "manifest.json"

    try:
        strategy_config = load_strategy_from_registry(
            config.strategy_id,
            base_dir=config.strategies_dir,
        )
        symbols = _resolve_symbols(config.symbols, strategy_config.universe)
        market_data = _load_or_build_market_data(config, symbols, warnings)
        market_data.to_csv(market_data_path, index=False)

        strategy_input = (
            build_features(market_data)
            if config.build_features
            else market_data.copy()
        )
        if config.build_features:
            features_path = run_dir / "features.csv"
            strategy_input.to_csv(features_path, index=False)

        strategy = instantiate_strategy(strategy_config)
        signal_df, _ = strategy.generate_signals(strategy_input)
        signals_path = run_dir / "signals.csv"
        signal_df.to_csv(signals_path, index=False)

        from aurora.models.labels import create_forward_return_label

        label_config = {"price_col": "close", "horizon": 5}
        try:
            labeled = create_forward_return_label(strategy_input, **label_config)
            label_series = labeled.set_index("timestamp")["future_return_5d"]
        except Exception:
            label_series = pd.Series(dtype=float)

        feature_files = [
            str(run_dir / "features.csv"),
        ]

        if resolved_config.skip_leakage_check:
            warnings.append("leakage_check_skipped=skip_leakage_check=True")
            leakage_report = {}
            leakage_verdict = "UNKNOWN"
        else:
            leakage_report: dict[str, Any] = {}
            leakage_verdict = "UNKNOWN"
            try:
                if "symbol" in strategy_input.columns:
                    first_symbol = strategy_input["symbol"].iloc[0]
                    label_filtered = labeled[labeled["symbol"] == first_symbol].set_index("timestamp")["future_return_5d"]
                    features_filtered = strategy_input[strategy_input["symbol"] == first_symbol].copy()
                else:
                    label_filtered = label_series
                    features_filtered = strategy_input.copy()
                feature_subset = features_filtered[["timestamp", "close"] + [c for c in features_filtered.columns if c in ("return_1d", "return_5d", "return_20d", "rsi_14", "macd", "volume_change_1d")]].copy()
                feature_subset = feature_subset.rename(columns={"timestamp": "_ts"}).set_index("_ts").sort_index()
                leakage_feature_df = feature_subset
                try:
                    if leakage_feature_df.empty:
                        raise ValueError("Feature DataFrame is empty")
                    if label_filtered.empty:
                        raise ValueError("Label series is empty")
                    if len(leakage_feature_df.index) < 30:
                        raise ValueError(f"Insufficient data: {len(leakage_feature_df.index)} rows")
                    leakage_report = check_leakage_for_run(
                        run_dir=str(run_dir),
                        feature_df=leakage_feature_df,
                        label_series=label_filtered,
                        feature_files=feature_files,
                        horizon_days=5,
                        p_value_threshold=0.001,
                        bonferroni_correction=True,
                        correlation_threshold=0.3,
                    )
                    leakage_verdict = leakage_report.get("verdict", "UNKNOWN")
                    warnings.append(f"leakage_verdict={leakage_verdict}")
                except Exception as inner_exc:
                    warnings.append(f"leakage_check_skipped={inner_exc}")
            except LeakageError:
                raise
            except Exception as exc:
                warnings.append(f"leakage_check_skipped={exc}")

        backtest_result = _run_backtest(signal_df, config, strategy_config.risk)
        equity_path = run_dir / "equity_curve.csv"
        trades_path = run_dir / "trades.csv"
        backtest_result.equity_curve.to_csv(equity_path, index=False)
        backtest_result.trades.to_csv(trades_path, index=False)

        metrics = metrics_to_dict(backtest_result.metrics)
        backtest_path = save_json_report(
            {
                "research_only": True,
                "metrics": metrics,
                "backtest_config": asdict(backtest_result.config),
                "equity_curve_path": str(equity_path),
                "trades_path": str(trades_path),
            },
            run_dir / "backtest.json",
        )

        diagnostic_report = diagnose_backtest_overfitting(
            metrics,
            trades=backtest_result.trades,
            equity_curve=backtest_result.equity_curve,
        )
        diagnostics = overfitting_report_to_dict(diagnostic_report)
        diagnostics_path = save_json_report(diagnostics, run_dir / "diagnostics.json")
        warnings.extend(_diagnostic_messages(diagnostics))

        report_path = _write_summary_report(
            run_dir=run_dir,
            config=resolved_config,
            metrics=metrics,
            diagnostics=diagnostics,
            warnings=warnings,
        )
    except (
        AuroraBacktestError,
        AuroraDataError,
        SignalGenerationError,
        StrategyConfigError,
        StrategyRegistryError,
        ValueError,
    ) as exc:
        raise ResearchRunError(f"Research run failed: {exc}") from exc

    completed_at = datetime.now(UTC).isoformat()
    artifact_paths = {
        "config": str(config_path),
        "market_data": str(market_data_path),
        "features": str(features_path) if features_path is not None else None,
        "signals": str(signals_path),
        "equity_curve": str(equity_path),
        "trades": str(trades_path),
        "backtest": str(backtest_path),
        "diagnostics": str(diagnostics_path),
        "manifest": str(manifest_path),
        "report": str(report_path) if report_path is not None else None,
    }
    manifest = _build_manifest(
        run_id=run_id,
        config=resolved_config,
        symbols=symbols,
        started_at=started_at,
        completed_at=completed_at,
        artifact_paths=artifact_paths,
        metrics=metrics,
        diagnostics=diagnostics,
        warnings=warnings,
        leakage_report=leakage_report,
    )
    save_json_report(manifest, manifest_path)

    result = ResearchRunResult(
        run_id=run_id,
        strategy_id=config.strategy_id,
        symbols=symbols,
        started_at=started_at,
        completed_at=completed_at,
        output_dir=str(run_dir),
        config_path=str(config_path),
        signals_path=str(signals_path),
        backtest_path=str(backtest_path),
        diagnostics_path=str(diagnostics_path),
        manifest_path=str(manifest_path),
        report_path=str(report_path) if report_path is not None else None,
        metrics=metrics,
        diagnostics=diagnostics,
        warnings=warnings,
    )
    artifact_warnings = validate_research_run_artifacts(result)
    if artifact_warnings:
        warnings.extend(artifact_warnings)
        result = replace(result, warnings=warnings)
        manifest["warnings"] = warnings
        save_json_report(manifest, manifest_path)
    return result


def validate_research_run_artifacts(result: ResearchRunResult) -> list[str]:
    """Return warnings for missing research run artifacts."""
    warnings: list[str] = []
    required_paths = {
        "config_path": result.config_path,
        "signals_path": result.signals_path,
        "backtest_path": result.backtest_path,
        "diagnostics_path": result.diagnostics_path,
        "manifest_path": result.manifest_path,
    }
    for field_name, path in required_paths.items():
        if not path or not Path(path).exists():
            warnings.append(f"Missing required research artifact: {field_name}={path}")

    if result.report_path and not Path(result.report_path).exists():
        warnings.append(f"Missing optional research artifact: report_path={result.report_path}")
    return warnings


def _validate_config(config: ResearchRunConfig) -> None:
    if not config.strategy_id.strip():
        raise ResearchRunError("strategy_id must be non-empty.")
    if config.initial_cash <= 0:
        raise ResearchRunError("initial_cash must be greater than 0.")
    if config.commission_bps < 0:
        raise ResearchRunError("commission_bps must be non-negative.")
    if config.slippage_bps < 0:
        raise ResearchRunError("slippage_bps must be non-negative.")
    if config.max_position_pct is not None and config.max_position_pct <= 0:
        raise ResearchRunError("max_position_pct must be greater than 0 when supplied.")
    if config.data_mode not in SUPPORTED_DATA_MODES:
        supported = ", ".join(sorted(SUPPORTED_DATA_MODES))
        raise ResearchRunError(
            f"Unsupported data_mode: {config.data_mode}. Use one of: {supported}."
        )


def _create_run_dir(config: ResearchRunConfig) -> tuple[str, Path]:
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = (
        _slugify(config.run_id)
        if config.run_id
        else generate_research_run_id(config.strategy_id)
    )
    if not run_id:
        raise ResearchRunError("run_id must contain at least one filesystem-safe character.")

    run_dir = output_dir / run_id
    if config.run_id and run_dir.exists():
        raise ResearchRunError(f"Research run already exists: {run_dir}")
    base_run_id = run_id
    counter = 2
    while run_dir.exists():
        run_id = f"{base_run_id}-{counter}"
        run_dir = output_dir / run_id
        counter += 1
    run_dir.mkdir(parents=True)
    return run_id, run_dir


def _resolve_symbols(config_symbols: list[str] | None, universe: dict[str, Any]) -> list[str]:
    if config_symbols:
        symbols = _clean_symbols(config_symbols)
    else:
        symbols = _clean_symbols(universe.get("symbols") or [])
    if not symbols:
        raise ResearchRunError("No symbols supplied in ResearchRunConfig or strategy universe.")
    return symbols


def _load_or_build_market_data(
    config: ResearchRunConfig,
    symbols: list[str],
    warnings: list[str],
) -> pd.DataFrame:
    cached = _load_cached_market_data(config, symbols, warnings)
    if cached is not None:
        return cached

    if config.data_mode == DATA_MODE_CACHE_ONLY:
        raise ResearchRunError(
            "data_mode cache_only found missing cached data for the requested symbols/date range. "
            "Preload data into the local cache or retry with --data-mode download_if_missing "
            "to allow research data retrieval."
        )

    if not config.start_date:
        raise ResearchRunError(
            "data_mode download_if_missing requires start_date when missing cached data."
        )

    source = YFinanceDataSource()
    request = MarketDataRequest(symbols=symbols, start=config.start_date, end=config.end_date)
    market_data = source.get_bars(request)
    key = cache_key("yfinance", symbols, config.start_date, config.end_date, "1d")
    save_market_data(market_data, key, base_dir=_cache_dir(config))
    warnings.append(f"Downloaded market data with yfinance and cached it as {key}.")
    return _filter_market_data(market_data, config, symbols)


def _load_cached_market_data(
    config: ResearchRunConfig,
    symbols: list[str],
    warnings: list[str],
) -> pd.DataFrame | None:
    cache_dir = _cache_dir(config)
    if config.start_date:
        key = cache_key("yfinance", symbols, config.start_date, config.end_date, "1d")
        exact = load_market_data(key, base_dir=cache_dir)
        if exact is not None:
            warnings.append(f"Loaded market data from cache key {key}.")
            return _filter_market_data(exact, config, symbols)

    if not cache_dir.exists():
        return None

    for path in sorted(cache_dir.glob("*.csv")):
        candidate = pd.read_csv(path)
        if "timestamp" in candidate.columns:
            candidate["timestamp"] = pd.to_datetime(candidate["timestamp"], errors="coerce")
        if not set(STANDARD_OHLCV_COLUMNS).issubset(candidate.columns):
            continue
        try:
            filtered = _filter_market_data(candidate, config, symbols)
        except ResearchRunError:
            continue
        filtered_symbols = set(filtered["symbol"].astype(str).str.upper())
        if not filtered.empty and set(symbols).issubset(filtered_symbols):
            warnings.append(f"Loaded market data from matching cache file {path.name}.")
            return filtered
    return None


def _filter_market_data(
    df: pd.DataFrame,
    config: ResearchRunConfig,
    symbols: list[str],
) -> pd.DataFrame:
    working = df.copy()
    if "timestamp" not in working.columns or "symbol" not in working.columns:
        raise ResearchRunError("Market data must contain timestamp and symbol columns.")
    working["timestamp"] = pd.to_datetime(working["timestamp"], errors="coerce")
    working["symbol"] = working["symbol"].astype(str).str.upper()
    working = working[working["symbol"].isin(symbols)]
    if config.start_date:
        working = working[working["timestamp"] >= pd.Timestamp(config.start_date)]
    if config.end_date:
        working = working[working["timestamp"] <= pd.Timestamp(config.end_date)]
    if working.empty:
        raise ResearchRunError("Market data is empty after symbol/date filtering.")
    return working.sort_values(["symbol", "timestamp"]).reset_index(drop=True)


def _run_backtest(
    signal_df: pd.DataFrame,
    config: ResearchRunConfig,
    strategy_risk: dict[str, Any],
) -> BacktestResult:
    max_position_pct = float(
        config.max_position_pct
        if config.max_position_pct is not None
        else strategy_risk.get("max_position_pct", 0.05)
    )
    backtest_config = BacktestConfig(
        starting_cash=config.initial_cash,
        position_size_pct=max_position_pct,
        max_position_pct=max_position_pct,
        commission_per_trade=_commission_bps_to_fixed(
            config.initial_cash,
            config.commission_bps,
        ),
        slippage_bps=config.slippage_bps,
    )
    return SimpleLongOnlyBacktester(backtest_config).run(signal_df)


def _write_summary_report(
    run_dir: Path,
    config: ResearchRunConfig,
    metrics: dict[str, Any],
    diagnostics: dict[str, Any],
    warnings: list[str],
) -> Path | None:
    if not config.write_report:
        return None
    return save_markdown_report(
        "AURORA Research Run",
        {
            "Research Safety": (
                "Research-only workflow. Generated artifacts are not profitability claims "
                "and no trades or orders were placed."
            ),
            "Run": research_run_config_to_dict(config),
            "Metrics": metrics,
            "Diagnostics": diagnostics,
            "Warnings": warnings,
        },
        run_dir / "report.md",
    )


def _build_manifest(
    run_id: str,
    config: ResearchRunConfig,
    symbols: list[str],
    started_at: str,
    completed_at: str,
    artifact_paths: dict[str, str | None],
    metrics: dict[str, Any],
    diagnostics: dict[str, Any],
    warnings: list[str],
    leakage_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "run_id": run_id,
        "strategy_id": config.strategy_id,
        "created_at": started_at,
        "completed_at": completed_at,
        "data_mode": config.data_mode,
        "symbols": symbols,
        "start_date": config.start_date,
        "end_date": config.end_date,
        "artifact_paths": artifact_paths,
        "metrics_summary": metrics,
        "diagnostics_summary": {
            "ok": diagnostics.get("ok"),
            "issue_count": len(diagnostics.get("issues", [])),
            "summary": diagnostics.get("summary", {}),
        },
        "warnings": list(warnings),
        "safety_flags": dict(RESEARCH_RUN_SAFETY_FLAGS),
    }

    if leakage_report:
        manifest["leakage_verdict"] = leakage_report.get("verdict", "UNKNOWN")
        manifest["leakage_verified"] = leakage_report.get("verdict") == "CLEAN"
        if leakage_report.get("verdict") == "COMPROMISED":
            manifest["safety_flags"] = manifest.get("safety_flags", {})
            manifest["safety_flags"]["leakage_detected"] = True
        if "leakage_report_path" in leakage_report:
            manifest["leakage_report_path"] = leakage_report["leakage_report_path"]

    return manifest


def _diagnostic_messages(diagnostics: dict[str, Any]) -> list[str]:
    messages = []
    for issue in diagnostics.get("issues", []):
        severity = issue.get("severity", "warning")
        code = issue.get("code", "diagnostic")
        message = issue.get("message", "")
        messages.append(f"{severity}:{code}: {message}")
    return messages


def _cache_dir(config: ResearchRunConfig) -> Path:
    return Path(config.data_dir) / "cache"


def _clean_symbols(symbols: list[str]) -> list[str]:
    cleaned: list[str] = []
    for symbol in symbols:
        normalized = str(symbol).strip().upper()
        if normalized and normalized not in cleaned:
            cleaned.append(normalized)
    return cleaned


def _commission_bps_to_fixed(initial_cash: float, commission_bps: float) -> float:
    # The v1 backtester accepts fixed per-trade commission, so the orchestration
    # uses initial cash as a transparent basis for bps-style run configuration.
    return float(initial_cash * (commission_bps / 10000))


def _slugify(value: str | None) -> str:
    if value is None:
        return ""
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower())
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")
