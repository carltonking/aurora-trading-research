"""Deterministic local demo workflow for AURORA artifacts."""

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from aurora.data.cache import cache_key, save_market_data
from aurora.readiness.paper_sim import (
    PaperSimReadinessConfig,
    evaluate_paper_sim_readiness,
)
from aurora.readiness.paper_sim_plan import PaperSimPlanConfig, create_paper_sim_plan
from aurora.reporting.artifact_packet import ArtifactPacketConfig, build_artifact_packet
from aurora.reporting.safety_audit import SafetyAuditConfig, run_safety_boundary_audit
from aurora.reporting.status_snapshot import (
    ProjectStatusSnapshotConfig,
    create_project_status_snapshot,
)
from aurora.research.run import ResearchRunConfig, run_research_cycle
from aurora.review.board import ReviewBoardConfig, review_research_run
from aurora.strategies.base import StrategyConfig
from aurora.strategies.registry import save_strategy_config

DEFAULT_DEMO_SYMBOLS = ["SPY", "QQQ", "DIA"]
DEMO_START_DATE = "2020-01-01"
DEMO_SAFETY_FLAGS = {
    "demo_only": True,
    "synthetic_data": True,
    "placed_orders": False,
    "used_broker": False,
    "wrote_ledger": False,
    "external_llm_calls": False,
}


@dataclass(frozen=True)
class DemoWorkflowConfig:
    """Configuration for the deterministic local demo workflow."""

    output_root: str = "data/demo"
    strategy_id: str = "demo_momentum_strategy"
    symbols: list[str] | None = None
    rows: int = 260
    latest_test_count: int | None = None
    create_packet_zip: bool = True
    run_safety_audit: bool = True


@dataclass(frozen=True)
class DemoWorkflowResult:
    """Paths and safety metadata produced by the local demo workflow."""

    output_root: str
    strategy_id: str
    symbols: list[str]
    data_dir: str
    strategies_dir: str
    research_run_dir: str
    manifest_path: str
    review_path: str
    readiness_path: str
    plan_path: str
    packet_manifest_path: str
    packet_zip_path: str | None
    status_json_path: str
    status_markdown_path: str
    safety_audit_json_path: str | None
    safety_audit_markdown_path: str | None
    warnings: list[str]
    safety_flags: dict[str, Any]


class DemoWorkflowError(Exception):
    """Raised when the local demo workflow cannot complete."""


def run_demo_workflow(config: DemoWorkflowConfig) -> DemoWorkflowResult:
    """Run a local, synthetic-data-only artifact workflow."""
    symbols = _resolve_symbols(config.symbols)
    _validate_config(config, symbols)

    output_root = Path(config.output_root)
    data_dir = output_root / "data"
    strategies_dir = output_root / "strategies"
    research_runs_dir = output_root / "research_runs"
    status_dir = output_root / "status"

    try:
        _write_synthetic_market_data(data_dir, symbols, config.rows)
        strategy = _demo_strategy_config(config.strategy_id, symbols)
        save_strategy_config(strategy, base_dir=strategies_dir)

        research_result = run_research_cycle(
            ResearchRunConfig(
                strategy_id=config.strategy_id,
                symbols=symbols,
                start_date=DEMO_START_DATE,
                data_mode="cache_only",
                data_dir=str(data_dir),
                strategies_dir=str(strategies_dir),
                output_dir=str(research_runs_dir),
                build_features=True,
                write_report=True,
                skip_leakage_check=True,
            )
        )
        run_dir = Path(research_result.output_dir)

        review_result = review_research_run(ReviewBoardConfig(run_dir=str(run_dir)))
    except Exception as exc:
        raise DemoWorkflowError(f"Demo workflow failed during research setup: {exc}") from exc

    try:
        readiness_result = evaluate_paper_sim_readiness(
            PaperSimReadinessConfig(run_dir=str(run_dir))
        )
    except Exception as exc:
        raise DemoWorkflowError(f"Demo workflow failed during readiness evaluation: {exc}") from exc

    try:
        plan_result = create_paper_sim_plan(PaperSimPlanConfig(run_dir=str(run_dir)))
        packet_result = build_artifact_packet(
            ArtifactPacketConfig(
                run_dir=str(run_dir),
                create_zip=config.create_packet_zip,
            )
        )
        status_result = create_project_status_snapshot(
            ProjectStatusSnapshotConfig(
                output_dir=str(status_dir),
                research_runs_dir=str(research_runs_dir),
                latest_test_count=config.latest_test_count,
            )
        )
        safety_audit_result = (
            run_safety_boundary_audit(
                SafetyAuditConfig(
                    source_dir="src/aurora",
                    output_dir=str(status_dir),
                    fail_on_critical=False,
                )
            )
            if config.run_safety_audit
            else None
        )
    except Exception as exc:
        raise DemoWorkflowError(f"Demo workflow failed while writing artifacts: {exc}") from exc

    warnings = list(research_result.warnings)
    warnings.extend(_finding_messages("review", review_result.findings))
    warnings.extend(_finding_messages("readiness", readiness_result.findings))
    warnings.extend(_finding_messages("plan", plan_result.findings))
    warnings.extend(_finding_messages("packet", packet_result.findings))

    return DemoWorkflowResult(
        output_root=str(output_root),
        strategy_id=config.strategy_id,
        symbols=symbols,
        data_dir=str(data_dir),
        strategies_dir=str(strategies_dir),
        research_run_dir=str(run_dir),
        manifest_path=str(research_result.manifest_path),
        review_path=str(review_result.output_path),
        readiness_path=str(readiness_result.output_path),
        plan_path=str(plan_result.output_path),
        packet_manifest_path=str(packet_result.packet_manifest_path),
        packet_zip_path=packet_result.zip_path,
        status_json_path=str(status_result.json_path),
        status_markdown_path=str(status_result.markdown_path),
        safety_audit_json_path=(
            str(safety_audit_result.json_path) if safety_audit_result is not None else None
        ),
        safety_audit_markdown_path=(
            str(safety_audit_result.markdown_path) if safety_audit_result is not None else None
        ),
        warnings=warnings,
        safety_flags=dict(DEMO_SAFETY_FLAGS),
    )


def demo_workflow_result_to_dict(result: DemoWorkflowResult) -> dict[str, Any]:
    """Convert a demo workflow result to a JSON-serializable dictionary."""
    return asdict(result)


def _resolve_symbols(symbols: list[str] | None) -> list[str]:
    resolved = symbols or DEFAULT_DEMO_SYMBOLS
    cleaned: list[str] = []
    for symbol in resolved:
        normalized = str(symbol).strip().upper()
        if normalized and normalized not in cleaned:
            cleaned.append(normalized)
    return cleaned


def _validate_config(config: DemoWorkflowConfig, symbols: list[str]) -> None:
    if not config.strategy_id.strip():
        raise DemoWorkflowError("strategy_id must be non-empty.")
    if not symbols:
        raise DemoWorkflowError("At least one demo symbol is required.")
    if config.rows < 60:
        raise DemoWorkflowError("rows must be at least 60 for the demo workflow.")


def _write_synthetic_market_data(data_dir: Path, symbols: list[str], rows: int) -> Path:
    key = cache_key("yfinance", symbols, DEMO_START_DATE, None, "1d")
    return save_market_data(
        _synthetic_ohlcv(symbols, rows),
        key,
        base_dir=data_dir / "cache",
    )


def _synthetic_ohlcv(symbols: list[str], rows: int) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    dates = pd.date_range(DEMO_START_DATE, periods=rows, freq="D")
    symbol_offsets = {symbol: index * 7.5 for index, symbol in enumerate(symbols)}
    for symbol in symbols:
        price = 100.0 + symbol_offsets[symbol]
        for index, timestamp in enumerate(dates):
            phase = index % 12
            daily_move = 0.018 if phase < 6 else -0.016
            price = max(10.0, price * (1.0 + daily_move))
            open_price = price * (1.0 - (daily_move / 2.0))
            high_price = max(open_price, price) * 1.004
            low_price = min(open_price, price) * 0.996
            records.append(
                {
                    "timestamp": timestamp,
                    "symbol": symbol,
                    "open": round(open_price, 6),
                    "high": round(high_price, 6),
                    "low": round(low_price, 6),
                    "close": round(price, 6),
                    "adjusted_close": round(price, 6),
                    "volume": 1_000_000 + (index * 1000) + int(symbol_offsets[symbol] * 10),
                    "source": "synthetic_demo",
                    "asset_type": "etf",
                    "currency": "USD",
                }
            )
    return pd.DataFrame(records)


def _demo_strategy_config(strategy_id: str, symbols: list[str]) -> StrategyConfig:
    return StrategyConfig(
        strategy_id=strategy_id,
        name="Demo Momentum Strategy",
        strategy_type="momentum",
        asset_class="etf",
        universe={"symbols": symbols},
        timeframe="1d",
        direction="long_only",
        entry_rules=[{"return_col": "return_5d", "min_return": 0.0}],
        exit_rules=[{"type": "signal_flat"}],
        risk={
            "max_position_pct": 0.05,
            "allow_shorting": False,
            "allow_margin": False,
        },
        validation={
            "require_walk_forward": True,
            "min_trades": 50,
            "include_slippage": True,
            "include_transaction_costs": True,
        },
        metadata={
            "generated_by": "demo_workflow",
            "synthetic_data": True,
            "status": "demo",
        },
    )


def _finding_messages(prefix: str, findings: list[Any]) -> list[str]:
    messages = []
    for finding in findings:
        severity = getattr(finding, "severity", "INFO")
        code = getattr(finding, "code", "finding")
        message = getattr(finding, "message", "")
        if severity != "INFO":
            messages.append(f"{prefix}:{severity}:{code}: {message}")
    return messages
