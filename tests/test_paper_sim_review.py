import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from aurora.cli.app import app
from aurora.execution.paper_sim_review import (
    PAPER_SIM_REVIEW_FAIL,
    PAPER_SIM_REVIEW_PASS,
    PAPER_SIM_REVIEW_WARN,
    PaperSimReviewConfig,
    paper_sim_review_result_to_dict,
    review_paper_simulation,
)
from aurora.risk.models import (
    RISK_APPROVED,
    RISK_KILL_SWITCH_TRIGGERED,
    RISK_REDUCED_SIZE,
    RISK_REJECTED,
)


def test_missing_simulation_manifest_fails_when_required(tmp_path) -> None:
    run_dir = _write_simulation(tmp_path, write_manifest=False)

    result = review_paper_simulation(PaperSimReviewConfig(run_dir=str(run_dir)))

    assert result.status == PAPER_SIM_REVIEW_FAIL
    assert any(finding.code == "missing_simulation_manifest" for finding in result.findings)


def test_missing_simulation_manifest_warns_when_not_required(tmp_path) -> None:
    run_dir = _write_simulation(tmp_path, write_manifest=False)

    result = review_paper_simulation(
        PaperSimReviewConfig(run_dir=str(run_dir), require_simulation_manifest=False)
    )

    assert result.status == PAPER_SIM_REVIEW_WARN
    assert any(finding.code == "missing_simulation_manifest" for finding in result.findings)


def test_unsafe_simulation_safety_flag_fails(tmp_path) -> None:
    run_dir = _write_simulation(tmp_path, safety_flags={"real_broker_used": True})

    result = review_paper_simulation(PaperSimReviewConfig(run_dir=str(run_dir)))

    assert result.status == PAPER_SIM_REVIEW_FAIL
    assert any(finding.code == "unsafe_simulation_safety_flag" for finding in result.findings)


def test_missing_orders_fails_when_required(tmp_path) -> None:
    run_dir = _write_simulation(tmp_path, write_orders=False)

    result = review_paper_simulation(PaperSimReviewConfig(run_dir=str(run_dir)))

    assert result.status == PAPER_SIM_REVIEW_FAIL
    assert any(finding.code == "missing_orders" for finding in result.findings)


def test_missing_risk_decisions_fails_when_required(tmp_path) -> None:
    run_dir = _write_simulation(tmp_path, write_risk_decisions=False)

    result = review_paper_simulation(PaperSimReviewConfig(run_dir=str(run_dir)))

    assert result.status == PAPER_SIM_REVIEW_FAIL
    assert any(finding.code == "missing_risk_decisions" for finding in result.findings)


def test_kill_switch_decision_fails_by_default(tmp_path) -> None:
    run_dir = _write_simulation(
        tmp_path,
        risk_decisions=[_risk_decision(RISK_KILL_SWITCH_TRIGGERED)],
        orders=[_order("REJECTED", RISK_KILL_SWITCH_TRIGGERED)],
    )

    result = review_paper_simulation(PaperSimReviewConfig(run_dir=str(run_dir)))

    assert result.status == PAPER_SIM_REVIEW_FAIL
    assert result.summary["kill_switch_decisions"] == 1


def test_kill_switch_decision_warns_when_configured(tmp_path) -> None:
    run_dir = _write_simulation(
        tmp_path,
        risk_decisions=[_risk_decision(RISK_KILL_SWITCH_TRIGGERED)],
        orders=[_order("REJECTED", RISK_KILL_SWITCH_TRIGGERED)],
    )

    result = review_paper_simulation(
        PaperSimReviewConfig(run_dir=str(run_dir), fail_on_kill_switch=False)
    )

    assert result.status == PAPER_SIM_REVIEW_WARN
    assert any(finding.code == "kill_switch_decision" for finding in result.findings)


def test_high_rejected_order_ratio_warns(tmp_path) -> None:
    run_dir = _write_simulation(
        tmp_path,
        orders=[
            _order("REJECTED", RISK_REJECTED),
            _order("REJECTED", RISK_REJECTED),
            _order("FILLED", RISK_APPROVED),
        ],
        risk_decisions=[
            _risk_decision(RISK_REJECTED),
            _risk_decision(RISK_REJECTED),
            _risk_decision(RISK_APPROVED),
        ],
    )

    result = review_paper_simulation(PaperSimReviewConfig(run_dir=str(run_dir)))

    assert result.status == PAPER_SIM_REVIEW_WARN
    assert result.summary["rejected_order_ratio"] > 0.50
    assert any(finding.code == "high_rejected_order_ratio" for finding in result.findings)


def test_clean_local_simulation_artifacts_pass(tmp_path) -> None:
    run_dir = _write_simulation(tmp_path)

    result = review_paper_simulation(PaperSimReviewConfig(run_dir=str(run_dir)))

    assert result.status == PAPER_SIM_REVIEW_PASS
    assert result.summary["total_orders"] == 2
    assert result.summary["filled_orders"] == 2
    assert result.summary["total_risk_decisions"] == 2
    assert Path(result.output_path).exists()


def test_review_result_is_json_serializable(tmp_path) -> None:
    run_dir = _write_simulation(tmp_path)
    result = review_paper_simulation(PaperSimReviewConfig(run_dir=str(run_dir)))

    json.dumps(paper_sim_review_result_to_dict(result))


def test_cli_review_paper_sim_smoke(tmp_path) -> None:
    run_dir = _write_simulation(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["execution", "review-paper-sim", "--run-dir", str(run_dir)],
    )

    assert result.exit_code == 0, result.output
    assert "Paper simulation review analyzes local simulation artifacts only." in result.output
    assert "Paper Simulation Review" in result.output


def test_review_does_not_instantiate_broker_or_ledger(tmp_path, monkeypatch) -> None:
    run_dir = _write_simulation(tmp_path)

    class Forbidden:
        def __init__(self, *args, **kwargs) -> None:
            raise AssertionError("paper simulation review must not instantiate broker or ledger")

    monkeypatch.setattr("aurora.execution.simulation_broker.SimulationBroker", Forbidden)
    monkeypatch.setattr("aurora.execution.ledger.PaperLedger", Forbidden)

    result = review_paper_simulation(PaperSimReviewConfig(run_dir=str(run_dir)))

    assert result.status == PAPER_SIM_REVIEW_PASS


def test_review_does_not_modify_existing_ledger_artifacts(tmp_path) -> None:
    run_dir = _write_simulation(tmp_path)
    watched = _ledger_artifact_contents(run_dir)

    review_paper_simulation(PaperSimReviewConfig(run_dir=str(run_dir)))

    assert _ledger_artifact_contents(run_dir) == watched
    _assert_no_global_ledger(tmp_path)


def test_malformed_jsonl_line_warns_and_is_skipped(tmp_path) -> None:
    run_dir = _write_simulation(tmp_path)
    orders_path = run_dir / "paper_simulation" / "orders.jsonl"
    orders_path.write_text(orders_path.read_text(encoding="utf-8") + "{bad json\n", encoding="utf-8")

    result = review_paper_simulation(PaperSimReviewConfig(run_dir=str(run_dir)))

    assert result.status == PAPER_SIM_REVIEW_WARN
    assert any(finding.code == "malformed_orders_line" for finding in result.findings)


def _write_simulation(
    tmp_path,
    write_manifest: bool = True,
    write_orders: bool = True,
    write_risk_decisions: bool = True,
    write_account: bool = True,
    write_positions: bool = True,
    safety_flags: dict | None = None,
    orders: list[dict] | None = None,
    risk_decisions: list[dict] | None = None,
) -> Path:
    run_dir = tmp_path / "data" / "research_runs" / "run_1"
    simulation_dir = run_dir / "paper_simulation"
    simulation_dir.mkdir(parents=True)
    _write_json(run_dir / "manifest.json", {"run_id": "run_1", "strategy_id": "strategy_1"})

    resolved_flags = _simulation_safety_flags()
    if safety_flags:
        resolved_flags.update(safety_flags)
    if write_manifest:
        _write_json(
            simulation_dir / "simulation_manifest.json",
            {
                "run_id": "run_1",
                "strategy_id": "strategy_1",
                "status": "COMPLETED",
                "safety_flags": resolved_flags,
            },
        )
    if write_orders:
        _write_jsonl(simulation_dir / "orders.jsonl", orders or [_order(), _order()])
    if write_risk_decisions:
        _write_jsonl(
            simulation_dir / "risk_decisions.jsonl",
            risk_decisions or [_risk_decision(), _risk_decision()],
        )
    if write_account:
        _write_json(
            simulation_dir / "account.json",
            {"equity": 100100.0, "cash": 99000.0, "market_value": 1100.0},
        )
    if write_positions:
        _write_json(
            simulation_dir / "positions.json",
            {"SPY": {"symbol": "SPY", "quantity": 10.0, "average_price": 100.0}},
        )
    return run_dir


def _simulation_safety_flags() -> dict:
    return {
        "local_paper_simulation_only": True,
        "live_trading": False,
        "real_broker_used": False,
        "placed_real_orders": False,
        "external_llm_calls": False,
        "risk_gate_required": True,
        "dry_run": False,
    }


def _order(status: str = "FILLED", risk_status: str = RISK_APPROVED) -> dict:
    return {
        "order_id": "sim_000001",
        "symbol": "SPY",
        "side": "buy",
        "quantity": 1.0,
        "requested_quantity": 1.0,
        "price": 100.0,
        "fill_price": 100.0 if status == "FILLED" else None,
        "status": status,
        "timestamp": "2020-01-01T00:00:00+00:00",
        "strategy_id": "strategy_1",
        "risk_status": risk_status,
        "risk_reasons": ["fixture"],
    }


def _risk_decision(status: str = RISK_APPROVED) -> dict:
    return {
        "status": status,
        "approved": status in {RISK_APPROVED, RISK_REDUCED_SIZE},
        "original_quantity": 1.0,
        "final_quantity": 1.0 if status in {RISK_APPROVED, RISK_REDUCED_SIZE} else 0.0,
        "reasons": ["fixture"],
        "candidate": {"symbol": "SPY", "side": "buy", "quantity": 1.0, "price": 100.0},
    }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _ledger_artifact_contents(run_dir: Path) -> dict[str, str]:
    simulation_dir = run_dir / "paper_simulation"
    return {
        name: (simulation_dir / name).read_text(encoding="utf-8")
        for name in [
            "orders.jsonl",
            "risk_decisions.jsonl",
            "account.json",
            "positions.json",
        ]
    }


def _assert_no_global_ledger(tmp_path) -> None:
    ledger_dir = tmp_path / "data" / "ledger"
    for filename in [
        "orders.jsonl",
        "risk_decisions.jsonl",
        "account.json",
        "positions.json",
    ]:
        assert not (ledger_dir / filename).exists()
