"""Breakout strategy archetype using price channel breakout.

This is a research-only signal generator. No live trading, no broker calls.
"""

import pandas as pd


class BreakoutStrategy:
    """Breakout strategy using price channel breakout detection.

    Generates LONG signals when price breaks above the highest high
    within the lookback period.
    Generates FLAT signals otherwise.
    """

    def __init__(
        self,
        lookback_period: int = 20,
        price_column: str = "close",
        high_column: str = "high",
        signal_column: str = "signal",
        reason_column: str = "reason",
    ):
        """Initialize breakout strategy with parameters.

        Args:
            lookback_period: Number of periods to look back for breakout detection.
            price_column: Column name for price data (for confirmation).
            high_column: Column name for high prices.
            signal_column: Column name for output signal.
            reason_column: Column name for signal reason.
        """
        if lookback_period < 1:
            raise ValueError("lookback_period must be positive")

        self.lookback_period = lookback_period
        self.price_column = price_column
        self.high_column = high_column
        self.signal_column = signal_column
        self.reason_column = reason_column
        self.strategy_name = "breakout"

    def generate_signal(self, data: pd.DataFrame) -> pd.Series:
        """Generate breakout signals from OHLCV data.

        Args:
            data: DataFrame with price data. Must contain high_column.

        Returns:
            Series with signal values: 1 for LONG, 0 for FLAT.
        """
        if self.high_column not in data.columns:
            raise ValueError(f"Missing required column: {self.high_column}")

        df = data.copy()

        rolling_high = df[self.high_column].rolling(window=self.lookback_period).max()
        rolling_high_shifted = rolling_high.shift(1)

        signals = pd.Series(0, index=df.index, dtype=int)
        signals[df[self.high_column] > rolling_high_shifted] = 1

        df[self.signal_column] = signals
        df[self.reason_column] = signals.apply(
            lambda x: "price_broke_above_lookback_high" if x == 1 else "price_below_lookback_high"
        )

        return signals

    def get_params(self) -> dict:
        """Get strategy parameters as dictionary."""
        return {
            "lookback_period": self.lookback_period,
            "price_column": self.price_column,
            "high_column": self.high_column,
            "strategy_name": self.strategy_name,
        }

    def __repr__(self) -> str:
        return f"BreakoutStrategy(lookback_period={self.lookback_period})"