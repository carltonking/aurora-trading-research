"""Custom exceptions for backtesting workflows."""


class AuroraBacktestError(Exception):
    """Base exception for AURORA backtesting errors."""


class BacktestInputError(AuroraBacktestError):
    """Raised when backtest inputs are invalid."""


class BacktestCalculationError(AuroraBacktestError):
    """Raised when backtest calculations fail."""
