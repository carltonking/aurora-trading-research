import pytest

from aurora.reporting.exceptions import ReportLoadError
from aurora.reporting.reports import (
    generate_daily_summary_report,
    load_json_report,
    save_json_report,
    save_markdown_report,
)


def test_save_load_json_report_round_trips(tmp_path) -> None:
    payload = {"created_at": "2024-01-01T00:00:00", "summary": {"ok": True}}
    path = save_json_report(payload, tmp_path / "reports" / "report.json")

    loaded = load_json_report(path)

    assert loaded == payload


def test_save_markdown_report_writes_content(tmp_path) -> None:
    path = save_markdown_report(
        "AURORA Report",
        {"Account": {"equity": 100000}, "Notes": ["local only"]},
        tmp_path / "report.md",
    )

    content = path.read_text(encoding="utf-8")

    assert "# AURORA Report" in content
    assert "## Account" in content
    assert "equity" in content


def test_generate_daily_summary_report_returns_expected_top_level_keys() -> None:
    report = generate_daily_summary_report(
        account={"equity": 100000},
        positions={"AAPL": {"symbol": "AAPL", "quantity": 1, "market_price": 100}},
        orders=[{"status": "FILLED", "risk_status": "APPROVED", "symbol": "AAPL"}],
        risk_decisions=[{"status": "APPROVED", "approved": True}],
        backtest_metrics={"total_return": 0.01},
    )

    assert {
        "created_at",
        "account",
        "positions_summary",
        "orders_summary",
        "risk_summary",
        "backtest_summary",
    }.issubset(report)
    assert report["backtest_summary"]["total_return"] == 0.01


def test_invalid_or_missing_json_load_raises_report_load_error(tmp_path) -> None:
    with pytest.raises(ReportLoadError):
        load_json_report(tmp_path / "missing.json")

    invalid = tmp_path / "invalid.json"
    invalid.write_text("{invalid", encoding="utf-8")
    with pytest.raises(ReportLoadError):
        load_json_report(invalid)
