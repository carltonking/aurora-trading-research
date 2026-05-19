from aurora.validation.overfitting import OverfittingIssue, OverfittingReport
from aurora.validation.report import (
    load_validation_report,
    overfitting_report_to_dict,
    save_validation_report,
    walk_forward_result_to_dict,
)
from aurora.validation.walk_forward import WalkForwardConfig, run_walk_forward_validation
from tests.test_walk_forward_validation import _signal_df


def test_walk_forward_result_to_dict_returns_serializable_dictionary() -> None:
    result = run_walk_forward_validation(
        _signal_df(),
        WalkForwardConfig(n_splits=2, min_test_rows=10, min_trade_count=1),
    )

    payload = walk_forward_result_to_dict(result)

    assert payload["summary"]["window_count"] == 2
    assert payload["windows"][0]["window"]["window_id"] == "wf_1"


def test_overfitting_report_to_dict_returns_serializable_dictionary() -> None:
    report = OverfittingReport(
        ok=False,
        issues=[OverfittingIssue("error", "low_trade_count", "Too few trades.")],
        summary={"trade_count": 1},
        created_at="2026-01-01T00:00:00+00:00",
    )

    payload = overfitting_report_to_dict(report)

    assert payload["ok"] is False
    assert payload["issues"][0]["code"] == "low_trade_count"


def test_save_load_validation_report_round_trips(tmp_path) -> None:
    payload = {"ok": True, "summary": {"window_count": 2}}
    path = save_validation_report(payload, tmp_path / "validation" / "report.json")

    loaded = load_validation_report(path)

    assert loaded == payload
