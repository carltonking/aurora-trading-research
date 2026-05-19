import pandas as pd
import pytest

from aurora.backtesting.metrics import calculate_equity_curve_metrics, metrics_to_dict


def test_metrics_calculation_works_for_increasing_equity_curve() -> None:
    equity_curve = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=4),
            "equity": [100.0, 101.0, 102.0, 104.0],
            "cash": [100.0, 50.0, 50.0, 104.0],
            "market_value": [0.0, 51.0, 52.0, 0.0],
            "exposure": [0.0, 0.5, 0.5, 0.0],
        }
    )
    trades = pd.DataFrame({"net_pnl": [4.0]})

    metrics = calculate_equity_curve_metrics(equity_curve, trades, starting_cash=100.0)

    assert metrics.total_return == pytest.approx(0.04)
    assert metrics.annualized_return is not None
    assert metrics.max_drawdown == pytest.approx(0.0)
    assert metrics.win_rate == pytest.approx(1.0)
    assert metrics.trade_count == 1
    assert metrics.exposure_pct == pytest.approx(0.5)


def test_no_trade_case_handles_trade_metrics_gracefully() -> None:
    equity_curve = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=2),
            "equity": [100.0, 100.0],
            "cash": [100.0, 100.0],
            "market_value": [0.0, 0.0],
            "exposure": [0.0, 0.0],
        }
    )

    metrics = calculate_equity_curve_metrics(equity_curve, pd.DataFrame(), starting_cash=100.0)

    assert metrics.win_rate is None
    assert metrics.profit_factor is None
    assert metrics.trade_count == 0


def test_max_drawdown_is_calculated_correctly() -> None:
    equity_curve = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=4),
            "equity": [100.0, 120.0, 90.0, 110.0],
            "cash": [100.0, 120.0, 90.0, 110.0],
            "market_value": [0.0, 0.0, 0.0, 0.0],
            "exposure": [0.0, 0.0, 0.0, 0.0],
        }
    )

    metrics = calculate_equity_curve_metrics(equity_curve, pd.DataFrame(), starting_cash=100.0)

    assert metrics.max_drawdown == pytest.approx(-0.25)


def test_metrics_to_dict_returns_expected_keys() -> None:
    equity_curve = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=1),
            "equity": [100.0],
            "cash": [100.0],
            "market_value": [0.0],
            "exposure": [0.0],
        }
    )

    metrics = calculate_equity_curve_metrics(equity_curve, pd.DataFrame(), starting_cash=100.0)
    result = metrics_to_dict(metrics)

    assert "total_return" in result
    assert "final_equity" in result
    assert "starting_equity" in result
