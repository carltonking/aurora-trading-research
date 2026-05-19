"""Backtesting package."""

from aurora.backtesting.engine import BacktestConfig, BacktestResult, SimpleLongOnlyBacktester
from aurora.backtesting.metrics import (
    BacktestMetrics,
    calculate_equity_curve_metrics,
    metrics_to_dict,
)
from aurora.backtesting.trades import Position, Trade, trades_to_dataframe

__all__ = [
    "BacktestConfig",
    "BacktestMetrics",
    "BacktestResult",
    "Position",
    "SimpleLongOnlyBacktester",
    "Trade",
    "calculate_equity_curve_metrics",
    "metrics_to_dict",
    "trades_to_dataframe",
]
