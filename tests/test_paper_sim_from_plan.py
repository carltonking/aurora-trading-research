import json
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from aurora.cli.app import app
from aurora.execution.paper_sim_from_plan import (
    PAPER_SIM_FROM_PLAN_BLOCKED,
    PAPER_SIM_FROM_PLAN_COMPLETED,
    PaperSimFromPlanConfig,
    PaperSimFromPlanError,
    paper_sim_from_plan_result_to_dict,
    run_paper_simulation_from_plan,
)
from aurora.readiness.paper_sim import PAPER_SIM_BLOCKED, PAPER_SIM_READY
from aurora.readiness.paper_sim_plan import PAPER_SIM_PLAN_BLOCKED, PAPER_SIM_PLAN_READY
from aurora.risk.models import RISK_APPROVED, RiskDecision


def test_missing_manifest_raises(tmp_path) -> None:
    with pytest.raises(PaperSimFromPlanError, match="manifest"):
        run_paper_simulation_from_plan(PaperSimFromPlanConfig(run_dir=str(tmp_path)))


def test_missing_readiness_raises(tmp_path) -> None:
    run_dir = _write_run(tmp_path, write_readiness=False)

    with pytest.raises(PaperSimFromPlanError, match="Readiness"):
        run_paper_simulation_from_plan(PaperSimFromPlanConfig(run_dir=str(run_dir)))


def test_missing_plan_raises(tmp_path) -> None:
    run_dir = _write_run(tmp_path, write_plan=False)

    with pytest.raises(PaperSimFromPlanError, match="Plan"):
        run_paper_simulation_from_plan(PaperSimFromPlanConfig(run_dir=str(run_dir)))


def test_readiness_not_ready_blocks_when_required(tmp_path) -> None:
    run_dir = _write_run(tmp_path, readiness_status=PAPER_SIM_BLOCKED)

    result = run_paper_simulation_from_plan(PaperSimFromPlanConfig(run_dir=str(run_dir)))

    assert result.status == PAPER_SIM_FROM_PLAN_BLOCKED
    assert any(finding.code == "readiness_not_ready" for finding in result.findings)


def test_plan_not_ready_blocks_when_required(tmp_path) -> None:
    run_dir = _write_run(tmp_path, plan_status=PAPER_SIM_PLAN_BLOCKED)

    result = run_paper_simulation_from_plan(PaperSimFromPlanConfig(run_dir=str(run_dir)))

    assert result.status == PAPER_SIM_FROM_PLAN_BLOCKED
    assert any(finding.code == "plan_not_ready" for finding in result.findings)


def test_plan_without_risk_gate_blocks_when_required(tmp_path) -> None:
    run_dir = _write_run(tmp_path, require_risk_gate=False)

    result = run_paper_simulation_from_plan(PaperSimFromPlanConfig(run_dir=str(run_dir)))

    assert result.status == PAPER_SIM_FROM_PLAN_BLOCKED
    assert any(finding.code == "risk_gate_not_required_by_plan" for finding in result.findings)


def test_missing_signals_blocks(tmp_path) -> None:
    run_dir = _write_run(tmp_path, write_signals=False)

    result = run_paper_simulation_from_plan(PaperSimFromPlanConfig(run_dir=str(run_dir)))

    assert result.status == PAPER_SIM_FROM_PLAN_BLOCKED
    assert any(finding.code == "missing_signals_artifact" for finding in result.findings)


def test_dry_run_writes_manifest_but_no_ledger_artifacts(tmp_path) -> None:
    run_dir = _write_run(tmp_path)

    result = run_paper_simulation_from_plan(
        PaperSimFromPlanConfig(run_dir=str(run_dir), dry_run=True)
    )

    assert result.status == PAPER_SIM_FROM_PLAN_COMPLETED
    assert result.summary["dry_run"] is True
    assert Path(result.simulation_manifest_path).exists()
    assert result.orders_path is None
    assert result.risk_decisions_path is None
    assert not (run_dir / "paper_simulation" / "orders.jsonl").exists()
    _assert_no_global_ledger(tmp_path)


def test_local_simulation_writes_under_run_dir_not_global_ledger(tmp_path) -> None:
    run_dir = _write_run(tmp_path)

    result = run_paper_simulation_from_plan(PaperSimFromPlanConfig(run_dir=str(run_dir)))

    output_dir = run_dir / "paper_simulation"
    assert result.status == PAPER_SIM_FROM_PLAN_COMPLETED
    assert result.output_dir == str(output_dir)
    assert Path(result.orders_path).exists()
    assert Path(result.risk_decisions_path).exists()
    assert Path(result.account_path).exists()
    assert Path(result.positions_path).exists()
    assert result.summary["candidate_count"] == 2
    assert result.summary["risk_decision_count"] == 2
    _assert_no_global_ledger(tmp_path)


def test_unsafe_prior_safety_flags_block(tmp_path) -> None:
    run_dir = _write_run(tmp_path, safety_flags={"placed_orders": True})

    result = run_paper_simulation_from_plan(PaperSimFromPlanConfig(run_dir=str(run_dir)))

    assert result.status == PAPER_SIM_FROM_PLAN_BLOCKED
    assert any(finding.code == "unsafe_prior_safety_flag" for finding in result.findings)


def test_negative_and_flat_signals_are_not_converted_to_short_candidates(tmp_path) -> None:
    run_dir = _write_run(
        tmp_path,
        signals=pd.DataFrame(
            [
                _signal_row("2020-01-01", "SPY", -1, 100.0),
                _signal_row("2020-01-02", "SPY", 0, 101.0),
                _signal_row("2020-01-03", "SPY", 1, 102.0),
            ]
        ),
    )

    result = run_paper_simulation_from_plan(
        PaperSimFromPlanConfig(run_dir=str(run_dir), dry_run=True)
    )

    assert result.status == PAPER_SIM_FROM_PLAN_COMPLETED
    assert result.summary["candidate_count"] == 1
    assert any(finding.code == "non_long_signals_ignored" for finding in result.findings)


def test_every_candidate_passes_through_risk_manager(tmp_path, monkeypatch) -> None:
    run_dir = _write_run(tmp_path)
    calls = []

    class SpyRiskManager:
        def __init__(self, config=None) -> None:
            self.config = config

        def evaluate(self, candidate, portfolio):
            calls.append(candidate.symbol)
            return RiskDecision(
                status=RISK_APPROVED,
                approved=True,
                original_quantity=candidate.quantity,
                final_quantity=candidate.quantity,
                reasons=["spy approved"],
                candidate=candidate,
            )

    monkeypatch.setattr("aurora.execution.paper_sim_from_plan.RiskManager", SpyRiskManager)

    result = run_paper_simulation_from_plan(
        PaperSimFromPlanConfig(run_dir=str(run_dir), dry_run=True)
    )

    assert result.summary["candidate_count"] == 2
    assert calls == ["QQQ", "SPY"]


def test_max_candidates_limits_processed_candidates(tmp_path) -> None:
    run_dir = _write_run(tmp_path)

    result = run_paper_simulation_from_plan(
        PaperSimFromPlanConfig(run_dir=str(run_dir), max_candidates=1, dry_run=True)
    )

    assert result.summary["candidate_count"] == 1
    assert any(finding.code == "max_candidates_reached" for finding in result.findings)


def test_result_serialization_is_json_serializable(tmp_path) -> None:
    run_dir = _write_run(tmp_path)
    result = run_paper_simulation_from_plan(
        PaperSimFromPlanConfig(run_dir=str(run_dir), dry_run=True)
    )

    json.dumps(paper_sim_from_plan_result_to_dict(result))


def test_cli_paper_sim_from_plan_smoke(tmp_path) -> None:
    run_dir = _write_run(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "execution",
            "paper-sim-from-plan",
            "--run-dir",
            str(run_dir),
            "--dry-run",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Paper simulation from plan uses local simulation only." in result.output
    assert "simulation_manifest_path" in result.output


def _write_run(
    tmp_path,
    readiness_status: str = PAPER_SIM_READY,
    plan_status: str = PAPER_SIM_PLAN_READY,
    require_risk_gate: bool = True,
    write_manifest: bool = True,
    write_readiness: bool = True,
    write_plan: bool = True,
    write_signals: bool = True,
    safety_flags: dict | None = None,
    signals: pd.DataFrame | None = None,
) -> Path:
    run_dir = tmp_path / "data" / "research_runs" / "run_1"
    run_dir.mkdir(parents=True)
    resolved_flags = _safe_flags()
    if safety_flags:
        resolved_flags.update(safety_flags)

    signals_path = run_dir / "signals.csv"
    if write_signals:
        (signals if signals is not None else _signals()).to_csv(signals_path, index=False)

    if write_manifest:
        _write_json(
            run_dir / "manifest.json",
            {
                "run_id": "run_1",
                "strategy_id": "strategy_1",
                "safety_flags": resolved_flags,
                "artifact_paths": {"signals": str(signals_path)},
            },
        )
    if write_readiness:
        _write_json(
            run_dir / "paper_sim_readiness.json",
            {
                "run_id": "run_1",
                "strategy_id": "strategy_1",
                "status": readiness_status,
                "safety_flags": resolved_flags,
                "metrics": {"trade_count": 50, "max_drawdown": -0.01},
            },
        )
    if write_plan:
        _write_json(
            run_dir / "paper_sim_plan.json",
            {
                "run_id": "run_1",
                "strategy_id": "strategy_1",
                "status": plan_status,
                "safety_flags": resolved_flags,
                "plan": {
                    "run_id": "run_1",
                    "strategy_id": "strategy_1",
                    "initial_cash": 100000.0,
                    "max_position_pct": 0.05,
                    "slippage_bps": 0.0,
                    "commission_bps": 0.0,
                    "require_risk_gate": require_risk_gate,
                    "proposed_input_artifacts": {"signals_path": str(signals_path)},
                },
            },
        )
    return run_dir


def _signals() -> pd.DataFrame:
    return pd.DataFrame(
        [
            _signal_row("2020-01-01", "SPY", 1, 100.0),
            _signal_row("2020-01-01", "QQQ", 1, 200.0),
            _signal_row("2020-01-02", "SPY", 0, 101.0),
        ]
    )


def _signal_row(timestamp: str, symbol: str, signal: int, price: float) -> dict:
    return {
        "timestamp": timestamp,
        "symbol": symbol,
        "signal": signal,
        "adjusted_close": price,
        "close": price,
        "asset_type": "etf",
    }


def _safe_flags() -> dict:
    return {
        "research_only": True,
        "placed_orders": False,
        "used_broker": False,
        "wrote_ledger": False,
        "external_llm_calls": False,
    }


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _assert_no_global_ledger(tmp_path) -> None:
    ledger_dir = tmp_path / "data" / "ledger"
    for filename in [
        "orders.jsonl",
        "risk_decisions.jsonl",
        "account.json",
        "positions.json",
    ]:
        assert not (ledger_dir / filename).exists()
