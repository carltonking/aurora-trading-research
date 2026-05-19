from datetime import UTC, datetime
import json
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from aurora.cli.app import app
from aurora.data.cache import cache_key, save_market_data
from aurora.research.run import (
    ResearchRunConfig,
    ResearchRunError,
    ResearchRunResult,
    generate_research_run_id,
    research_run_config_to_dict,
    research_run_result_to_dict,
    run_research_cycle,
    validate_research_run_artifacts,
)
from aurora.strategies.config import strategy_config_from_dict
from aurora.strategies.registry import save_strategy_config
from tests.test_strategy_config import valid_strategy_dict


def test_research_run_dataclass_serialization() -> None:
    config = ResearchRunConfig(strategy_id="momentum_test", symbols=["SPY"])
    result = ResearchRunResult(
        run_id="run_1",
        strategy_id="momentum_test",
        symbols=["SPY"],
        started_at="2026-01-01T00:00:00+00:00",
        completed_at="2026-01-01T00:01:00+00:00",
        output_dir="data/research_runs/run_1",
        config_path="config.json",
        signals_path="signals.csv",
        backtest_path="backtest.json",
        diagnostics_path="diagnostics.json",
        manifest_path="manifest.json",
        report_path="report.md",
        metrics={"trade_count": 1},
        diagnostics={"ok": False},
        warnings=["low trade count"],
    )

    assert research_run_config_to_dict(config)["strategy_id"] == "momentum_test"
    serialized = research_run_result_to_dict(result)
    assert serialized["manifest_path"] == "manifest.json"
    assert serialized["warnings"] == ["low trade count"]
    json.dumps(serialized)


def test_generate_research_run_id_includes_timestamp_and_strategy_slug() -> None:
    run_id = generate_research_run_id(
        "Momentum Test",
        datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
    )

    assert run_id == "20260102T030405Z_momentum-test"


@pytest.mark.parametrize(
    ("strategy_id", "expected_slug"),
    [
        ("My Strategy 01", "my-strategy-01"),
        ("ml/signal:test", "ml-signal-test"),
        ("AURORA Strategy!", "aurora-strategy"),
    ],
)
def test_generate_research_run_id_slugifies_unusual_strategy_ids(
    strategy_id: str,
    expected_slug: str,
) -> None:
    run_id = generate_research_run_id(
        strategy_id,
        datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
    )

    assert run_id == f"20260102T030405Z_{expected_slug}"


def test_research_run_creates_output_directory_and_config(tmp_path) -> None:
    result = _run_basic_cycle(tmp_path)

    output_dir = tmp_path / "runs" / result.run_id
    assert output_dir.exists()
    assert (output_dir / "config.json").exists()
    assert (output_dir / "signals.csv").exists()
    assert (output_dir / "backtest.json").exists()
    assert (output_dir / "diagnostics.json").exists()
    assert (output_dir / "manifest.json").exists()
    assert result.config_path == str(output_dir / "config.json")
    assert result.manifest_path == str(output_dir / "manifest.json")


def test_manifest_includes_safety_flags(tmp_path) -> None:
    result = _run_basic_cycle(tmp_path)

    manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))

    assert manifest["data_mode"] == "cache_only"
    assert manifest["safety_flags"] == {
        "research_only": True,
        "placed_orders": False,
        "used_broker": False,
        "wrote_ledger": False,
        "external_llm_calls": False,
    }
    assert manifest["artifact_paths"]["manifest"] == result.manifest_path


def test_explicit_symbols_override_strategy_symbols(tmp_path) -> None:
    result = _run_basic_cycle(tmp_path, symbols=["SPY"], strategy_symbols=["AAPL"])

    assert result.symbols == ["SPY"]


def test_missing_symbols_fails_clearly(tmp_path) -> None:
    strategies_dir = tmp_path / "strategies"
    data = valid_strategy_dict("momentum")
    data["strategy_id"] = "filter_only"
    data["universe"] = {"filters": {"asset_class": "equity"}}
    save_strategy_config(strategy_config_from_dict(data), base_dir=strategies_dir)

    config = ResearchRunConfig(
        strategy_id="filter_only",
        start_date="2020-01-01",
        data_dir=str(tmp_path / "data"),
        strategies_dir=str(strategies_dir),
        output_dir=str(tmp_path / "runs"),
    )

    with pytest.raises(ResearchRunError, match="No symbols"):
        run_research_cycle(config)


def test_research_run_result_contains_warnings_and_does_not_create_ledger(tmp_path) -> None:
    result = _run_basic_cycle(tmp_path)

    assert isinstance(result.warnings, list)
    assert result.warnings
    ledger_dir = tmp_path / "data" / "ledger"
    assert not (ledger_dir / "orders.jsonl").exists()
    assert not (ledger_dir / "risk_decisions.jsonl").exists()
    assert not (ledger_dir / "account.json").exists()
    assert not (ledger_dir / "positions.json").exists()


def test_cache_only_does_not_call_yfinance_when_cache_exists(tmp_path, monkeypatch) -> None:
    class FailingSource:
        def __init__(self) -> None:
            raise AssertionError("cache_only should not instantiate a data source")

    monkeypatch.setattr("aurora.research.run.YFinanceDataSource", FailingSource)

    result = _run_basic_cycle(tmp_path)

    assert result.symbols == ["SPY"]


def test_cache_only_missing_data_fails_clearly(tmp_path, monkeypatch) -> None:
    class FailingSource:
        def __init__(self) -> None:
            raise AssertionError("cache_only should not instantiate a data source")

    monkeypatch.setattr("aurora.research.run.YFinanceDataSource", FailingSource)
    strategies_dir = tmp_path / "strategies"
    _save_momentum_strategy(strategies_dir, strategy_id="momentum_missing", symbols=["SPY"])

    expected_error = "cache_only.*missing cached data.*download_if_missing"
    with pytest.raises(ResearchRunError, match=expected_error):
        run_research_cycle(
            ResearchRunConfig(
                strategy_id="momentum_missing",
                symbols=["SPY"],
                start_date="2020-01-01",
                data_dir=str(tmp_path / "data"),
                strategies_dir=str(strategies_dir),
                output_dir=str(tmp_path / "runs"),
            )
        )


def test_invalid_data_mode_fails_validation() -> None:
    with pytest.raises(ResearchRunError, match="Unsupported data_mode"):
        run_research_cycle(
            ResearchRunConfig(
                strategy_id="momentum_test",
                data_mode="live_download",
            )
        )


def test_download_if_missing_uses_mocked_download_path(tmp_path, monkeypatch) -> None:
    class FakeSource:
        def get_bars(self, request):
            assert request.symbols == ["SPY"]
            assert request.start == "2020-01-01"
            return _sample_ohlcv(["SPY"])

    monkeypatch.setattr("aurora.research.run.YFinanceDataSource", FakeSource)
    strategies_dir = tmp_path / "strategies"
    _save_momentum_strategy(strategies_dir, strategy_id="momentum_download", symbols=["SPY"])

    result = run_research_cycle(
        ResearchRunConfig(
            strategy_id="momentum_download",
            symbols=["SPY"],
            start_date="2020-01-01",
            data_mode="download_if_missing",
            data_dir=str(tmp_path / "data"),
            strategies_dir=str(strategies_dir),
            output_dir=str(tmp_path / "runs"),
        )
    )

    assert result.symbols == ["SPY"]
    assert any("Downloaded market data" in warning for warning in result.warnings)
    assert any((tmp_path / "data" / "cache").glob("*.csv"))


def test_validate_research_run_artifacts_catches_missing_required_artifact(tmp_path) -> None:
    result = _run_basic_cycle(tmp_path)
    Path(result.diagnostics_path).unlink()

    warnings = validate_research_run_artifacts(result)

    assert any("Missing required research artifact: diagnostics_path" in item for item in warnings)


def test_cli_research_run_smoke(tmp_path) -> None:
    strategies_dir = tmp_path / "strategies"
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "runs"
    _save_momentum_strategy(strategies_dir, strategy_id="momentum_cli", symbols=["SPY"])
    _save_cached_market_data(data_dir, symbols=["SPY"])

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "research",
            "run",
            "--strategy-id",
            "momentum_cli",
            "--symbols",
            "SPY",
            "--start-date",
            "2020-01-01",
            "--data-mode",
            "cache_only",
            "--data-dir",
            str(data_dir),
            "--strategies-dir",
            str(strategies_dir),
            "--output-dir",
            str(output_dir),
            "--no-write-report",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Research run completed without placing orders or using a broker." in result.output
    assert "manifest_path" in result.output
    assert any(path.name == "config.json" for path in output_dir.glob("*/config.json"))


def _run_basic_cycle(
    tmp_path,
    symbols: list[str] | None = None,
    strategy_symbols: list[str] | None = None,
):
    strategies_dir = tmp_path / "strategies"
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "runs"
    resolved_symbols = symbols or ["SPY"]
    _save_momentum_strategy(
        strategies_dir,
        strategy_id="momentum_test",
        symbols=strategy_symbols or resolved_symbols,
    )
    _save_cached_market_data(data_dir, symbols=resolved_symbols)

    return run_research_cycle(
        ResearchRunConfig(
            strategy_id="momentum_test",
            symbols=symbols,
            start_date="2020-01-01",
            data_dir=str(data_dir),
            strategies_dir=str(strategies_dir),
            output_dir=str(output_dir),
        )
    )


def _save_momentum_strategy(path, strategy_id: str, symbols: list[str]) -> None:
    data = valid_strategy_dict("momentum")
    data["strategy_id"] = strategy_id
    data["universe"] = {"symbols": symbols}
    save_strategy_config(strategy_config_from_dict(data), base_dir=path)


def _save_cached_market_data(data_dir, symbols: list[str]) -> None:
    df = _sample_ohlcv(symbols)
    key = cache_key("yfinance", symbols, "2020-01-01", None, "1d")
    save_market_data(df, key, base_dir=data_dir / "cache")


def _sample_ohlcv(symbols: list[str], rows: int = 45) -> pd.DataFrame:
    records = []
    dates = pd.date_range("2020-01-01", periods=rows, freq="D")
    for symbol in symbols:
        for index, timestamp in enumerate(dates):
            price = 100.0 + index
            records.append(
                {
                    "timestamp": timestamp,
                    "symbol": symbol,
                    "open": price,
                    "high": price + 1.0,
                    "low": price - 1.0,
                    "close": price,
                    "adjusted_close": price,
                    "volume": 1000 + index,
                    "source": "test",
                    "asset_type": "equity",
                    "currency": "USD",
                }
            )
    return pd.DataFrame(records)
