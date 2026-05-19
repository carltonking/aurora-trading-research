import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from aurora.cli.app import app
from aurora.review.board import (
    REVIEW_APPROVED_FOR_PAPER_SIMULATION,
    REVIEW_CRITICAL,
    REVIEW_NEEDS_MORE_RESEARCH,
    REVIEW_REJECTED,
    REVIEW_WARNING,
    ReviewBoardConfig,
    ReviewBoardError,
    review_board_result_to_dict,
    review_research_run,
)


def test_missing_manifest_raises_review_board_error(tmp_path) -> None:
    with pytest.raises(ReviewBoardError, match="manifest not found"):
        review_research_run(ReviewBoardConfig(run_dir=str(tmp_path)))


def test_unsafe_safety_flag_rejects_with_critical_finding(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path, safety_flags={"placed_orders": True})

    result = review_research_run(ReviewBoardConfig(run_dir=str(run_dir)))

    assert result.status == REVIEW_REJECTED
    assert _has_finding(result, "unsafe_manifest_safety_flag", REVIEW_CRITICAL)


def test_missing_backtest_rejects_with_critical_finding(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path, write_backtest=False)

    result = review_research_run(ReviewBoardConfig(run_dir=str(run_dir)))

    assert result.status == REVIEW_REJECTED
    assert _has_finding(result, "missing_backtest", REVIEW_CRITICAL)


def test_missing_diagnostics_required_rejects(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path, write_diagnostics=False)

    result = review_research_run(ReviewBoardConfig(run_dir=str(run_dir)))

    assert result.status == REVIEW_REJECTED
    assert _has_finding(result, "missing_diagnostics", REVIEW_CRITICAL)


def test_missing_diagnostics_optional_needs_more_research(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path, write_diagnostics=False)

    result = review_research_run(
        ReviewBoardConfig(run_dir=str(run_dir), require_diagnostics=False)
    )

    assert result.status == REVIEW_NEEDS_MORE_RESEARCH
    assert _has_finding(result, "missing_diagnostics", REVIEW_WARNING)


def test_low_trade_count_needs_more_research(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path, metrics={"trade_count": 10, "max_drawdown": -0.05})

    result = review_research_run(ReviewBoardConfig(run_dir=str(run_dir), min_trades=50))

    assert result.status == REVIEW_NEEDS_MORE_RESEARCH
    assert _has_finding(result, "low_trade_count", REVIEW_WARNING)


def test_zero_trades_rejected(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path, metrics={"trade_count": 0, "max_drawdown": 0.0})

    result = review_research_run(ReviewBoardConfig(run_dir=str(run_dir)))

    assert result.status == REVIEW_REJECTED
    assert _has_finding(result, "zero_trades", REVIEW_CRITICAL)


def test_max_drawdown_breach_needs_more_research(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path, metrics={"trade_count": 80, "max_drawdown": -0.35})

    result = review_research_run(ReviewBoardConfig(run_dir=str(run_dir), max_drawdown_pct=0.25))

    assert result.status == REVIEW_NEEDS_MORE_RESEARCH
    assert _has_finding(result, "max_drawdown_breach", REVIEW_WARNING)


def test_clean_artifacts_can_approve_for_paper_simulation(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path)

    result = review_research_run(ReviewBoardConfig(run_dir=str(run_dir)))

    assert result.status == REVIEW_APPROVED_FOR_PAPER_SIMULATION
    assert result.findings == []


def test_no_paper_approval_caps_best_status(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path)

    result = review_research_run(
        ReviewBoardConfig(run_dir=str(run_dir), allow_paper_simulation_approval=False)
    )

    assert result.status == REVIEW_NEEDS_MORE_RESEARCH


def test_profit_guarantee_language_in_report_warns(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path, report_text="This is a guaranteed profit.")

    result = review_research_run(ReviewBoardConfig(run_dir=str(run_dir)))

    assert result.status == REVIEW_NEEDS_MORE_RESEARCH
    assert _has_finding(result, "profit_guarantee_language", REVIEW_WARNING)


def test_diagnostics_issues_warn(tmp_path) -> None:
    diagnostics = {
        "ok": False,
        "issues": [
            {
                "severity": "warning",
                "code": "high_sharpe_ratio",
                "message": "Sharpe ratio is unusually high.",
            }
        ],
        "summary": {"window_count": 4},
    }
    run_dir = _write_run_artifacts(tmp_path, diagnostics=diagnostics)

    result = review_research_run(ReviewBoardConfig(run_dir=str(run_dir)))

    assert result.status == REVIEW_NEEDS_MORE_RESEARCH
    assert _has_finding(result, "diagnostic_high_sharpe_ratio", REVIEW_WARNING)


def test_review_board_result_to_dict_is_json_serializable(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path)
    result = review_research_run(ReviewBoardConfig(run_dir=str(run_dir)))

    payload = review_board_result_to_dict(result)
    encoded = json.dumps(payload)

    assert "APPROVED_FOR_PAPER_SIMULATION" in encoded


def test_review_json_is_written_to_default_path(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path)

    result = review_research_run(ReviewBoardConfig(run_dir=str(run_dir)))

    assert result.output_path == str(run_dir / "review.json")
    assert (run_dir / "review.json").exists()


def test_cli_review_run_smoke(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path)
    runner = CliRunner()

    result = runner.invoke(app, ["review", "run", "--run-dir", str(run_dir)])

    assert result.exit_code == 0, result.output
    assert "Review Board does not trade, place orders, or approve live trading." in result.output
    assert "APPROVED_FOR_PAPER_SIMULATION" in result.output
    assert "review.json" in result.output


def test_review_does_not_create_ledger_files(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path)

    review_research_run(ReviewBoardConfig(run_dir=str(run_dir)))

    ledger_dir = tmp_path / "data" / "ledger"
    assert not (ledger_dir / "orders.jsonl").exists()
    assert not (ledger_dir / "risk_decisions.jsonl").exists()
    assert not (ledger_dir / "account.json").exists()
    assert not (ledger_dir / "positions.json").exists()


def _write_run_artifacts(
    tmp_path,
    metrics: dict | None = None,
    diagnostics: dict | None = None,
    safety_flags: dict | None = None,
    report_text: str = "Research-only report.",
    write_backtest: bool = True,
    write_diagnostics: bool = True,
) -> Path:
    run_dir = tmp_path / "runs" / "run_1"
    run_dir.mkdir(parents=True)
    resolved_metrics = metrics or {"trade_count": 80, "max_drawdown": -0.10}
    resolved_diagnostics = diagnostics or {"ok": True, "issues": [], "summary": {"window_count": 4}}
    resolved_safety_flags = {
        "research_only": True,
        "placed_orders": False,
        "used_broker": False,
        "wrote_ledger": False,
        "external_llm_calls": False,
    }
    if safety_flags:
        resolved_safety_flags.update(safety_flags)

    if write_backtest:
        _write_json(run_dir / "backtest.json", {"metrics": resolved_metrics})
    if write_diagnostics:
        _write_json(run_dir / "diagnostics.json", resolved_diagnostics)
    (run_dir / "report.md").write_text(report_text, encoding="utf-8")

    _write_json(
        run_dir / "manifest.json",
        {
            "run_id": "run_1",
            "strategy_id": "strategy_1",
            "artifact_paths": {
                "backtest": str(run_dir / "backtest.json"),
                "diagnostics": str(run_dir / "diagnostics.json"),
                "report": str(run_dir / "report.md"),
            },
            "metrics_summary": resolved_metrics,
            "diagnostics_summary": resolved_diagnostics.get("summary", {}),
            "safety_flags": resolved_safety_flags,
        },
    )
    return run_dir


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def _has_finding(result, code: str, severity: str) -> bool:
    return any(finding.code == code and finding.severity == severity for finding in result.findings)
