"""Dollar-cost averaging (DCA) strategy archetype.

This is a research-only signal generator. No live trading, no broker calls.
"""

import pandas as pd
from datetime import datetime, timedelta


class DollarCostAveragingStrategy:
    """Dollar-cost averaging strategy - buy at regular intervals.

    Generates LONG signals at each interval boundary (first trading day
    of month/week/etc.). Generates FLAT signals otherwise.
    """

    def __init__(
        self,
        interval: str = "monthly",
        amount: float = 1000.0,
        price_column: str = "close",
        signal_column: str = "signal",
        reason_column: str = "reason",
    ):
        """Initialize DCA strategy with parameters.

        Args:
            interval: Interval for purchases - "daily", "weekly", "monthly".
            amount: Fixed dollar amount per purchase (for reference, not used in signals).
            price_column: Column name for price data.
            signal_column: Column name for output signal.
            reason_column: Column name for signal reason.
        """
        valid_intervals = {"daily", "weekly", "monthly"}
        if interval not in valid_intervals:
            raise ValueError(f"interval must be one of {valid_intervals}")

        self.interval = interval
        self.amount = amount
        self.price_column = price_column
        self.signal_column = signal_column
        self.reason_column = reason_column
        self.strategy_name = "dca"

    def __repr__(self) -> str:
        return f"DollarCostAveragingStrategy(interval={self.interval}, amount={self.amount})"

    def generate_signal(self, data: pd.DataFrame) -> pd.Series:
        """Generate DCA signals from OHLCV data.

        Args:
            data: DataFrame with price data. Must contain price_column.

        Returns:
            Series with signals: 1 for buy intervals, 0 for hold.
        """
        if self.price_column not in data.columns:
            raise ValueError(f"Price column '{self.price_column}' not found in data")

        signals = pd.Series(0, index=data.index)
        reasons = pd.Series("", index=data.index)

        if not isinstance(data.index, pd.DatetimeIndex):
            return signals

        prev_period = None

        for i in range(len(data)):
            current_date = data.index[i]
            current_period = self._get_period(current_date)

            if prev_period is not None and current_period != prev_period:
                signals.iloc[i] = 1
                reasons.iloc[i] = f"dca_{self.interval}_{current_period}"

            prev_period = current_period

        result = data.copy()
        result[self.signal_column] = signals
        result[self.reason_column] = reasons
        return result[self.signal_column]

    def _get_period(self, date: pd.Timestamp) -> str:
        """Get the period identifier for a date."""
        if self.interval == "daily":
            return date.strftime("%Y-%m-%d")
        elif self.interval == "weekly":
            return date.strftime("%Y-W%W")
        elif self.interval == "monthly":
            return date.strftime("%Y-%m")
        return ""