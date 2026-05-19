import json
from pathlib import Path

import pandas as pd

from aurora.data.cache import cache_key, save_market_data
from aurora.readiness.paper_sim import (
    PAPER_SIM_READY,
    PaperSimReadinessConfig,
    evaluate_paper_sim_readiness,
    paper_sim_readiness_result_to_dict,
)
from aurora.readiness.paper_sim_plan import (
    PAPER_SIM_PLAN_READY,
    PaperSimPlanConfig,
    create_paper_sim_plan,
    paper_sim_plan_result_to_dict,
)
from aurora.reporting.artifact_packet import (
    ARTIFACT_PACKET_COMPLETE,
    ARTIFACT_PACKET_PARTIAL,
    ArtifactPacketConfig,
    artifact_packet_result_to_dict,
    build_artifact_packet,
)
from aurora.reporting.safety_audit import (
    SAFETY_AUDIT_PASS,
    SafetyAuditConfig,
    safety_audit_result_to_dict,
    run_safety_boundary_audit,
)
from aurora.reporting.status_snapshot import (
    ProjectStatusSnapshotConfig,
    create_project_status_snapshot,
    project_status_snapshot_result_to_dict,
)
from aurora.research.run import ResearchRunConfig, research_run_result_to_dict, run_research_cycle
from aurora.review.board import (
    REVIEW_APPROVED_FOR_PAPER_SIMULATION,
    REVIEW_NEEDS_MORE_RESEARCH,
    ReviewBoardConfig,
    review_board_result_to_dict,
    review_research_run,
)
from aurora.strategies.config import strategy_config_from_dict, validate_strategy_config
from aurora.strategies.registry import save_strategy_config


def test_local_artifact_workflow_runs_without_network_or_execution(tmp_path, monkeypatch) -> None:
    _forbid_network_and_execution(monkeypatch)
    root = tmp_path / "data"
    strategies_dir = root / "strategies"
    research_runs_dir = root / "research_runs"
    status_dir = root / "status"
    symbols = ["SPY"]

    strategy_config = strategy_config_from_dict(_safe_momentum_strategy_config(symbols))
    validate_strategy_config(strategy_config)
    save_strategy_config(strategy_config, base_dir=strategies_dir)
    _save_synthetic_cache(root, symbols)

    research_result = run_research_cycle(
        ResearchRunConfig(
            strategy_id=strategy_config.strategy_id,
            symbols=symbols,
            start_date="2020-01-01",
            data_mode="cache_only",
            data_dir=str(root),
            strategies_dir=str(strategies_dir),
            output_dir=str(research_runs_dir),
            commission_bps=10.0,
            slippage_bps=0.0,
            max_position_pct=0.05,
        )
    )
    run_dir = Path(research_result.output_dir)

    review_result = review_research_run(
        ReviewBoardConfig(
            run_dir=str(run_dir),
            min_trades=30,
            min_walk_forward_windows=0,
        )
    )
    readiness_result = evaluate_paper_sim_readiness(
        PaperSimReadinessConfig(
            run_dir=str(run_dir),
            min_trades=30,
        )
    )
    plan_result = create_paper_sim_plan(PaperSimPlanConfig(run_dir=str(run_dir)))
    packet_result = build_artifact_packet(ArtifactPacketConfig(run_dir=str(run_dir)))
    status_result = create_project_status_snapshot(
        ProjectStatusSnapshotConfig(
            output_dir=str(status_dir),
            research_runs_dir=str(research_runs_dir),
            latest_test_count=239,
        )
    )
    audit_source_dir = tmp_path / "audit_source"
    (audit_source_dir / "safe_module.py").parent.mkdir(parents=True)
    (audit_source_dir / "safe_module.py").write_text(
        "def research_only_marker() -> str:\n    return 'safe local fixture'\n",
        encoding="utf-8",
    )
    audit_result = run_safety_boundary_audit(
        SafetyAuditConfig(source_dir=str(audit_source_dir), output_dir=str(status_dir))
    )

    expected_paths = {
        "manifest": run_dir / "manifest.json",
        "review": run_dir / "review.json",
        "readiness": run_dir / "paper_sim_readiness.json",
        "plan": run_dir / "paper_sim_plan.json",
        "packet_manifest": run_dir / "artifact_packet" / "packet_manifest.json",
        "project_status_json": status_dir / "project_status.json",
        "project_status_md": status_dir / "project_status.md",
        "safety_audit_json": status_dir / "safety_audit.json",
        "safety_audit_md": status_dir / "safety_audit.md",
    }
    for path in expected_paths.values():
        assert path.exists(), path

    json_payloads = _read_json_payloads(
        {
            "manifest": expected_paths["manifest"],
            "review": expected_paths["review"],
            "readiness": expected_paths["readiness"],
            "plan": expected_paths["plan"],
            "packet_manifest": expected_paths["packet_manifest"],
            "project_status": expected_paths["project_status_json"],
            "safety_audit": expected_paths["safety_audit_json"],
        }
    )
    for payload in json_payloads.values():
        json.dumps(payload)

    assert review_result.status in {
        REVIEW_APPROVED_FOR_PAPER_SIMULATION,
        REVIEW_NEEDS_MORE_RESEARCH,
    }
    assert review_result.status == REVIEW_APPROVED_FOR_PAPER_SIMULATION
    assert readiness_result.status == PAPER_SIM_READY
    assert readiness_result.review_status == REVIEW_APPROVED_FOR_PAPER_SIMULATION
    assert readiness_result.status != "APPROVED_FOR_LIVE_TRADING"
    assert plan_result.status == PAPER_SIM_PLAN_READY
    assert plan_result.plan["safety_statement"] == (
        "This is a non-executing plan for future local paper simulation only."
    )
    assert packet_result.status in {ARTIFACT_PACKET_COMPLETE, ARTIFACT_PACKET_PARTIAL}
    assert _included_artifact_names(packet_result) >= {
        "manifest.json",
        "config.json",
        "signals.csv",
        "backtest.json",
        "diagnostics.json",
    }
    assert "paper_simulation/paper_sim_review.json" in packet_result.missing_artifacts
    assert audit_result.status == SAFETY_AUDIT_PASS
    assert status_result.recent_research_runs
    assert status_result.recent_research_runs[0]["run_id"] == research_result.run_id
    assert status_result.recent_research_runs[0]["packet_status"] == packet_result.status
    assert status_result.recent_research_runs[0]["paper_sim_review_path"] is None
    assert status_result.recent_research_runs[0]["paper_sim_review_status"] is None

    serialized_results = [
        research_run_result_to_dict(research_result),
        review_board_result_to_dict(review_result),
        paper_sim_readiness_result_to_dict(readiness_result),
        paper_sim_plan_result_to_dict(plan_result),
        artifact_packet_result_to_dict(packet_result),
        project_status_snapshot_result_to_dict(status_result),
        safety_audit_result_to_dict(audit_result),
    ]
    for payload in serialized_results:
        json.dumps(payload)

    for payload in json_payloads.values():
        if isinstance(payload.get("safety_flags"), dict):
            _assert_no_execution_safety_flags(payload["safety_flags"])

    assert json_payloads["manifest"]["data_mode"] == "cache_only"
    assert json_payloads["manifest"]["safety_flags"]["research_only"] is True
    assert json_payloads["plan"]["plan"]["prohibited_actions"] == [
        "live_trading",
        "broker_order_placement",
        "direct_prompt_order_placement",
        "external_llm_calls",
    ]
    assert not _ledger_files(root)


def _forbid_network_and_execution(monkeypatch) -> None:
    class ForbiddenDataSource:
        def __init__(self, *args, **kwargs) -> None:
            raise AssertionError("cache_only workflow must not instantiate market data sources")

    class ForbiddenExecution:
        def __init__(self, *args, **kwargs) -> None:
            raise AssertionError("artifact workflow must not instantiate execution or ledger APIs")

    monkeypatch.setattr("aurora.research.run.YFinanceDataSource", ForbiddenDataSource)
    monkeypatch.setattr("aurora.execution.simulation_broker.SimulationBroker", ForbiddenExecution)
    monkeypatch.setattr("aurora.execution.ledger.PaperLedger", ForbiddenExecution)


def _safe_momentum_strategy_config(symbols: list[str]) -> dict:
    return {
        "strategy_id": "e2e_momentum_fixture",
        "name": "E2E Momentum Fixture",
        "strategy_type": "momentum",
        "asset_class": "etf",
        "universe": {"symbols": symbols},
        "timeframe": "1d",
        "direction": "long_only",
        "entry_rules": [{"return_col": "return_5d", "min_return": 0.0}],
        "exit_rules": [],
        "risk": {
            "max_position_pct": 0.05,
            "allow_shorting": False,
            "allow_margin": False,
        },
        "validation": {
            "require_walk_forward": True,
            "min_trades": 30,
            "include_slippage": True,
            "include_transaction_costs": True,
        },
        "metadata": {"status": "fixture"},
    }


def _save_synthetic_cache(data_dir: Path, symbols: list[str]) -> None:
    key = cache_key("yfinance", symbols, "2020-01-01", None, "1d")
    save_market_data(
        _synthetic_ohlcv(symbols),
        key,
        base_dir=data_dir / "cache",
    )


def _synthetic_ohlcv(symbols: list[str], rows: int = 500) -> pd.DataFrame:
    records = []
    dates = pd.date_range("2020-01-01", periods=rows, freq="D")
    for symbol in symbols:
        price = 100.0
        for index, timestamp in enumerate(dates):
            phase = index % 12
            price *= 1.02 if phase < 6 else 0.98
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
                    "source": "synthetic_fixture",
                    "asset_type": "etf",
                    "currency": "USD",
                }
            )
    return pd.DataFrame(records)


def _read_json_payloads(paths: dict[str, Path]) -> dict[str, dict]:
    return {name: json.loads(path.read_text(encoding="utf-8")) for name, path in paths.items()}


def _assert_no_execution_safety_flags(flags: dict) -> None:
    assert flags["placed_orders"] is False
    assert flags["used_broker"] is False
    assert flags["wrote_ledger"] is False
    assert flags["external_llm_calls"] is False


def _included_artifact_names(packet_result) -> set[str]:
    return {artifact["name"] for artifact in packet_result.included_artifacts}


def _ledger_files(data_dir: Path) -> list[Path]:
    ledger_dir = data_dir / "ledger"
    return [
        path
        for path in [
        ledger_dir / "orders.jsonl",
        ledger_dir / "risk_decisions.jsonl",
        ledger_dir / "account.json",
        ledger_dir / "positions.json",
    ]
        if path.exists()
    ]
