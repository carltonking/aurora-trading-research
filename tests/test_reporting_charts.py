import pandas as pd

from aurora.reporting.charts import (
    drawdown_chart_data,
    equity_curve_chart_data,
    trade_pnl_chart_data,
)


def test_equity_curve_chart_data_sorts_and_returns_timestamp_equity() -> None:
    equity = pd.DataFrame(
        {
            "timestamp": ["2024-01-02", "2024-01-01"],
            "equity": [101.0, 100.0],
            "cash": [1, 1],
        }
    )

    result = equity_curve_chart_data(equity)

    assert list(result.columns) == ["timestamp", "equity"]
    assert result["equity"].tolist() == [100.0, 101.0]


def test_drawdown_chart_data_calculates_non_positive_drawdowns() -> None:
    equity = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=3),
            "equity": [100.0, 120.0, 90.0],
        }
    )

    result = drawdown_chart_data(equity)

    assert list(result.columns) == ["timestamp", "drawdown"]
    assert (result["drawdown"] <= 0).all()
    assert result["drawdown"].iloc[-1] == -0.25


def test_trade_pnl_chart_data_handles_present_and_missing_net_pnl() -> None:
    trades = pd.DataFrame({"trade_id": ["t1"], "symbol": ["AAPL"], "net_pnl": [10.0]})
    missing = pd.DataFrame({"trade_id": ["t1"], "symbol": ["AAPL"]})

    result = trade_pnl_chart_data(trades)
    empty = trade_pnl_chart_data(missing)

    assert result.to_dict("records") == [{"trade_id": "t1", "symbol": "AAPL", "net_pnl": 10.0}]
    assert empty.empty
    assert list(empty.columns) == ["trade_id", "symbol", "net_pnl"]
