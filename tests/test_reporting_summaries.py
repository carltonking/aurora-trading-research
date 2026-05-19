import pandas as pd

from aurora.reporting.summaries import (
    summarize_dataframe,
    summarize_orders,
    summarize_positions,
    summarize_risk_decisions,
)


def test_summarize_dataframe_with_timestamp_and_symbol() -> None:
    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2024-01-02", "2024-01-01"]),
            "symbol": ["MSFT", "AAPL"],
            "close": [101.0, 100.0],
            "note": ["b", "a"],
        }
    )

    summary = summarize_dataframe(df)

    assert summary["row_count"] == 2
    assert summary["column_count"] == 4
    assert summary["numeric_columns"] == ["close"]
    assert summary["symbols"] == ["AAPL", "MSFT"]
    assert summary["start_timestamp"].startswith("2024-01-01")
    assert summary["end_timestamp"].startswith("2024-01-02")


def test_summarize_orders_counts_filled_rejected_and_statuses() -> None:
    orders = [
        {
            "status": "FILLED",
            "risk_status": "APPROVED",
            "symbol": "AAPL",
            "timestamp": "2024-01-01T10:00:00",
        },
        {
            "status": "REJECTED",
            "risk_status": "REJECTED",
            "symbol": "MSFT",
            "timestamp": "2024-01-01T11:00:00",
        },
    ]

    summary = summarize_orders(orders)

    assert summary["order_count"] == 2
    assert summary["filled_count"] == 1
    assert summary["rejected_count"] == 1
    assert summary["symbols"] == ["AAPL", "MSFT"]
    assert summary["risk_status_counts"] == {"APPROVED": 1, "REJECTED": 1}
    assert summary["latest_timestamp"].startswith("2024-01-01T11:00:00")


def test_summarize_risk_decisions_counts_statuses() -> None:
    decisions = [
        {"status": "APPROVED", "approved": True, "candidate": {"timestamp": "2024-01-01T10:00:00"}},
        {"status": "REJECTED", "approved": False, "candidate": {"timestamp": "2024-01-01T11:00:00"}},
    ]

    summary = summarize_risk_decisions(decisions)

    assert summary["decision_count"] == 2
    assert summary["approved_count"] == 1
    assert summary["rejected_count"] == 1
    assert summary["status_counts"] == {"APPROVED": 1, "REJECTED": 1}
    assert summary["latest_timestamp"].startswith("2024-01-01T11:00:00")


def test_summarize_positions_works_with_dict_or_list() -> None:
    position_dict = {
        "AAPL": {"symbol": "AAPL", "quantity": 10.0, "market_price": 100.0},
        "MSFT": {"symbol": "MSFT", "quantity": 2.0, "market_price": 200.0},
    }
    position_list = list(position_dict.values())

    dict_summary = summarize_positions(position_dict)
    list_summary = summarize_positions(position_list)

    assert dict_summary["position_count"] == 2
    assert dict_summary["symbols"] == ["AAPL", "MSFT"]
    assert dict_summary["total_quantity"] == 12.0
    assert dict_summary["total_market_value"] == 1400.0
    assert list_summary == dict_summary
