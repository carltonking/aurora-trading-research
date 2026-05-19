import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from aurora.cli.app import app
from aurora.readiness.paper_sim import (
    PAPER_SIM_BLOCKED,
    PAPER_SIM_NEEDS_MORE_RESEARCH,
    PAPER_SIM_READY,
    READINESS_CRITICAL,
    READINESS_WARNING,
    PaperSimReadinessConfig,
    PaperSimReadinessError,
    evaluate_paper_sim_readiness,
    paper_sim_readiness_result_to_dict,
)


def test_missing_manifest_raises(tmp_path) -> None:
    run_dir = tmp_path / "data" / "research_runs" / "run_1"
    run_dir.mkdir(parents=True)

    with pytest.raises(PaperSimReadinessError, match="manifest not found"):
        evaluate_paper_sim_readiness(PaperSimReadinessConfig(run_dir=str(run_dir)))


def test_missing_review_raises(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path, write_review=False)

    with pytest.raises(PaperSimReadinessError, match="Review artifact not found"):
        evaluate_paper_sim_readiness(PaperSimReadinessConfig(run_dir=str(run_dir)))


def test_unsafe_manifest_safety_flag_blocks(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path, safety_flags={"used_broker": True})

    result = evaluate_paper_sim_readiness(PaperSimReadinessConfig(run_dir=str(run_dir)))

    assert result.status == PAPER_SIM_BLOCKED
    assert _has_finding(result, "unsafe_manifest_safety_flag", READINESS_CRITICAL)


def test_rejected_review_status_blocks(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path, review_status="REJECTED")

    result = evaluate_paper_sim_readiness(PaperSimReadinessConfig(run_dir=str(run_dir)))

    assert result.status == PAPER_SIM_BLOCKED
    assert _has_finding(result, "review_rejected", READINESS_CRITICAL)


def test_needs_more_research_review_blocks_when_approval_required(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path, review_status="NEEDS_MORE_RESEARCH")

    result = evaluate_paper_sim_readiness(PaperSimReadinessConfig(run_dir=str(run_dir)))

    assert result.status == PAPER_SIM_BLOCKED
    assert _has_finding(result, "review_status_below_required", READINESS_CRITICAL)


def test_needs_more_research_review_warns_when_approval_not_required(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path, review_status="NEEDS_MORE_RESEARCH")

    result = evaluate_paper_sim_readiness(
        PaperSimReadinessConfig(run_dir=str(run_dir), require_review_approval=False)
    )

    assert result.status == PAPER_SIM_NEEDS_MORE_RESEARCH
    assert _has_finding(result, "review_needs_more_research", READINESS_WARNING)


def test_critical_review_finding_blocks_when_required(tmp_path) -> None:
    run_dir = _write_run_artifacts(
        tmp_path,
        review_findings=[{"code": "unsafe_manifest_safety_flag", "severity": "CRITICAL"}],
    )

    result = evaluate_paper_sim_readiness(PaperSimReadinessConfig(run_dir=str(run_dir)))

    assert result.status == PAPER_SIM_BLOCKED
    assert _has_finding(result, "critical_review_finding", READINESS_CRITICAL)


def test_clean_approved_review_is_ready(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path)

    result = evaluate_paper_sim_readiness(PaperSimReadinessConfig(run_dir=str(run_dir)))

    assert result.status == PAPER_SIM_READY
    assert result.findings == []


def test_zero_trades_blocks(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path, metrics={"trade_count": 0, "max_drawdown": 0.0})

    result = evaluate_paper_sim_readiness(PaperSimReadinessConfig(run_dir=str(run_dir)))

    assert result.status == PAPER_SIM_BLOCKED
    assert _has_finding(result, "zero_trades", READINESS_CRITICAL)


def test_low_trade_count_needs_more_research(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path, metrics={"trade_count": 10, "max_drawdown": -0.05})

    result = evaluate_paper_sim_readiness(PaperSimReadinessConfig(run_dir=str(run_dir)))

    assert result.status == PAPER_SIM_NEEDS_MORE_RESEARCH
    assert _has_finding(result, "low_trade_count", READINESS_WARNING)


def test_drawdown_breach_needs_more_research(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path, metrics={"trade_count": 80, "max_drawdown": -0.35})

    result = evaluate_paper_sim_readiness(PaperSimReadinessConfig(run_dir=str(run_dir)))

    assert result.status == PAPER_SIM_NEEDS_MORE_RESEARCH
    assert _has_finding(result, "max_drawdown_breach", READINESS_WARNING)


def test_ledger_artifact_detection_blocks(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path)
    ledger_dir = tmp_path / "data" / "ledger"
    ledger_dir.mkdir(parents=True)
    (ledger_dir / "orders.jsonl").write_text("{}", encoding="utf-8")

    result = evaluate_paper_sim_readiness(PaperSimReadinessConfig(run_dir=str(run_dir)))

    assert result.status == PAPER_SIM_BLOCKED
    assert _has_finding(result, "ledger_artifact_detected", READINESS_CRITICAL)


def test_paper_sim_readiness_result_to_dict_is_json_serializable(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path)
    result = evaluate_paper_sim_readiness(PaperSimReadinessConfig(run_dir=str(run_dir)))

    payload = paper_sim_readiness_result_to_dict(result)
    encoded = json.dumps(payload)

    assert "READY_FOR_PAPER_SIMULATION" in encoded


def test_paper_sim_readiness_json_is_written_to_default_path(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path)

    result = evaluate_paper_sim_readiness(PaperSimReadinessConfig(run_dir=str(run_dir)))

    assert result.output_path == str(run_dir / "paper_sim_readiness.json")
    assert (run_dir / "paper_sim_readiness.json").exists()


def test_cli_paper_sim_readiness_smoke(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path)
    runner = CliRunner()

    result = runner.invoke(app, ["readiness", "paper-sim", "--run-dir", str(run_dir)])

    assert result.exit_code == 0, result.output
    assert "Paper simulation readiness does not trade" in result.output
    assert "READY_FOR_PAPER_SIMULATION" in result.output
    assert "paper_sim_readiness.json" in result.output


def test_readiness_gate_does_not_create_ledger_files(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path)

    evaluate_paper_sim_readiness(PaperSimReadinessConfig(run_dir=str(run_dir)))

    ledger_dir = tmp_path / "data" / "ledger"
    assert not (ledger_dir / "orders.jsonl").exists()
    assert not (ledger_dir / "risk_decisions.jsonl").exists()
    assert not (ledger_dir / "account.json").exists()
    assert not (ledger_dir / "positions.json").exists()


def _write_run_artifacts(
    tmp_path,
    metrics: dict | None = None,
    safety_flags: dict | None = None,
    review_status: str = "APPROVED_FOR_PAPER_SIMULATION",
    review_findings: list[dict] | None = None,
    write_review: bool = True,
) -> Path:
    run_dir = tmp_path / "data" / "research_runs" / "run_1"
    run_dir.mkdir(parents=True)
    resolved_metrics = metrics or {"trade_count": 80, "max_drawdown": -0.10}
    resolved_safety_flags = {
        "research_only": True,
        "placed_orders": False,
        "used_broker": False,
        "wrote_ledger": False,
        "external_llm_calls": False,
    }
    if safety_flags:
        resolved_safety_flags.update(safety_flags)

    _write_json(run_dir / "backtest.json", {"metrics": resolved_metrics})
    _write_json(run_dir / "diagnostics.json", {"ok": True, "issues": [], "summary": {}})
    _write_json(
        run_dir / "manifest.json",
        {
            "run_id": "run_1",
            "strategy_id": "strategy_1",
            "artifact_paths": {
                "backtest": str(run_dir / "backtest.json"),
                "diagnostics": str(run_dir / "diagnostics.json"),
            },
            "metrics_summary": resolved_metrics,
            "safety_flags": resolved_safety_flags,
        },
    )
    if write_review:
        _write_json(
            run_dir / "review.json",
            {
                "run_id": "run_1",
                "strategy_id": "strategy_1",
                "status": review_status,
                "findings": review_findings or [],
                "metrics": resolved_metrics,
            },
        )
    return run_dir


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def _has_finding(result, code: str, severity: str) -> bool:
    return any(finding.code == code and finding.severity == severity for finding in result.findings)
