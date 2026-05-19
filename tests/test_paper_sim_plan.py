import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from aurora.cli.app import app
from aurora.readiness.paper_sim_plan import (
    PAPER_SIM_PLAN_BLOCKED,
    PAPER_SIM_PLAN_READY,
    PLAN_CRITICAL,
    PaperSimPlanConfig,
    PaperSimPlanError,
    create_paper_sim_plan,
    paper_sim_plan_result_to_dict,
)


def test_missing_manifest_raises(tmp_path) -> None:
    run_dir = tmp_path / "data" / "research_runs" / "run_1"
    run_dir.mkdir(parents=True)

    with pytest.raises(PaperSimPlanError, match="manifest not found"):
        create_paper_sim_plan(PaperSimPlanConfig(run_dir=str(run_dir)))


def test_missing_review_raises(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path, write_review=False)

    with pytest.raises(PaperSimPlanError, match="Review artifact not found"):
        create_paper_sim_plan(PaperSimPlanConfig(run_dir=str(run_dir)))


def test_missing_readiness_raises(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path, write_readiness=False)

    with pytest.raises(PaperSimPlanError, match="Readiness artifact not found"):
        create_paper_sim_plan(PaperSimPlanConfig(run_dir=str(run_dir)))


def test_unsafe_manifest_safety_flag_blocks(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path, safety_flags={"placed_orders": True})

    result = create_paper_sim_plan(PaperSimPlanConfig(run_dir=str(run_dir)))

    assert result.status == PAPER_SIM_PLAN_BLOCKED
    assert _has_finding(result, "unsafe_manifest_safety_flag", PLAN_CRITICAL)


def test_blocked_readiness_blocks_when_required(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path, readiness_status="BLOCKED")

    result = create_paper_sim_plan(PaperSimPlanConfig(run_dir=str(run_dir)))

    assert result.status == PAPER_SIM_PLAN_BLOCKED
    assert _has_finding(result, "readiness_not_ready", PLAN_CRITICAL)


def test_needs_more_research_readiness_blocks_when_required(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path, readiness_status="NEEDS_MORE_RESEARCH")

    result = create_paper_sim_plan(PaperSimPlanConfig(run_dir=str(run_dir)))

    assert result.status == PAPER_SIM_PLAN_BLOCKED
    assert _has_finding(result, "readiness_not_ready", PLAN_CRITICAL)


def test_ready_artifacts_create_plan_ready(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path)

    result = create_paper_sim_plan(PaperSimPlanConfig(run_dir=str(run_dir)))

    assert result.status == PAPER_SIM_PLAN_READY
    assert result.plan["readiness_status"] == "READY_FOR_PAPER_SIMULATION"
    assert result.plan["review_status"] == "APPROVED_FOR_PAPER_SIMULATION"
    assert result.plan["proposed_input_artifacts"]["signals_path"] == str(run_dir / "signals.csv")


def test_missing_signals_blocks_when_required(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path, write_signals=False)

    result = create_paper_sim_plan(PaperSimPlanConfig(run_dir=str(run_dir)))

    assert result.status == PAPER_SIM_PLAN_BLOCKED
    assert _has_finding(result, "missing_signals_artifact", PLAN_CRITICAL)


def test_missing_signals_does_not_block_when_not_required(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path, write_signals=False)

    result = create_paper_sim_plan(
        PaperSimPlanConfig(run_dir=str(run_dir), require_signals_artifact=False)
    )

    assert result.status == PAPER_SIM_PLAN_READY
    assert result.signals_path is None


def test_plan_includes_prohibited_actions_and_safety_statement(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path)

    result = create_paper_sim_plan(PaperSimPlanConfig(run_dir=str(run_dir)))

    assert "live_trading" in result.plan["prohibited_actions"]
    assert "broker_order_placement" in result.plan["prohibited_actions"]
    assert "direct_prompt_order_placement" in result.plan["prohibited_actions"]
    assert "external_llm_calls" in result.plan["prohibited_actions"]
    assert result.plan["safety_statement"] == (
        "This is a non-executing plan for future local paper simulation only."
    )


def test_paper_sim_plan_result_to_dict_is_json_serializable(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path)
    result = create_paper_sim_plan(PaperSimPlanConfig(run_dir=str(run_dir)))

    payload = paper_sim_plan_result_to_dict(result)
    encoded = json.dumps(payload)

    assert "PLAN_READY" in encoded


def test_paper_sim_plan_json_is_written_to_default_path(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path)

    result = create_paper_sim_plan(PaperSimPlanConfig(run_dir=str(run_dir)))

    assert result.output_path == str(run_dir / "paper_sim_plan.json")
    assert (run_dir / "paper_sim_plan.json").exists()


def test_cli_paper_sim_plan_smoke(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path)
    runner = CliRunner()

    result = runner.invoke(app, ["readiness", "paper-sim-plan", "--run-dir", str(run_dir)])

    assert result.exit_code == 0, result.output
    assert "Paper simulation planning does not trade" in result.output
    assert "PLAN_READY" in result.output
    assert "paper_sim_plan.json" in result.output


def test_planning_does_not_create_ledger_files(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path)

    create_paper_sim_plan(PaperSimPlanConfig(run_dir=str(run_dir)))

    ledger_dir = tmp_path / "data" / "ledger"
    assert not (ledger_dir / "orders.jsonl").exists()
    assert not (ledger_dir / "risk_decisions.jsonl").exists()
    assert not (ledger_dir / "account.json").exists()
    assert not (ledger_dir / "positions.json").exists()


def _write_run_artifacts(
    tmp_path,
    readiness_status: str = "READY_FOR_PAPER_SIMULATION",
    review_status: str = "APPROVED_FOR_PAPER_SIMULATION",
    safety_flags: dict | None = None,
    write_review: bool = True,
    write_readiness: bool = True,
    write_signals: bool = True,
) -> Path:
    run_dir = tmp_path / "data" / "research_runs" / "run_1"
    run_dir.mkdir(parents=True)
    resolved_safety_flags = {
        "research_only": True,
        "placed_orders": False,
        "used_broker": False,
        "wrote_ledger": False,
        "external_llm_calls": False,
    }
    if safety_flags:
        resolved_safety_flags.update(safety_flags)

    if write_signals:
        (run_dir / "signals.csv").write_text("timestamp,symbol,signal\n", encoding="utf-8")
    _write_json(run_dir / "backtest.json", {"metrics": {"trade_count": 80}})
    _write_json(run_dir / "diagnostics.json", {"ok": True, "issues": [], "summary": {}})
    _write_json(
        run_dir / "manifest.json",
        {
            "run_id": "run_1",
            "strategy_id": "strategy_1",
            "symbols": ["SPY"],
            "artifact_paths": {
                "signals": str(run_dir / "signals.csv"),
                "backtest": str(run_dir / "backtest.json"),
                "diagnostics": str(run_dir / "diagnostics.json"),
            },
            "safety_flags": resolved_safety_flags,
        },
    )
    if write_review:
        _write_json(
            run_dir / "review.json",
            {"status": review_status, "findings": [], "metrics": {"trade_count": 80}},
        )
    if write_readiness:
        _write_json(
            run_dir / "paper_sim_readiness.json",
            {"status": readiness_status, "findings": []},
        )
    return run_dir


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def _has_finding(result, code: str, severity: str) -> bool:
    return any(finding.code == code and finding.severity == severity for finding in result.findings)
