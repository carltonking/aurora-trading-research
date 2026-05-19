"""Trend following strategy archetype using dual moving averages.

This is a research-only signal generator. No live trading, no broker calls.
"""

import pandas as pd


class TrendFollowingStrategy:
    """Trend following strategy using dual moving average crossover.

    Generates LONG signals when fast MA crosses above slow MA.
    Generates FLAT signals when fast MA is below slow MA.
    """

    def __init__(
        self,
        fast_window: int = 10,
        slow_window: int = 30,
        price_column: str = "close",
        signal_column: str = "signal",
        reason_column: str = "reason",
    ):
        """Initialize trend following strategy with parameters.

        Args:
            fast_window: Fast moving average window period.
            slow_window: Slow moving average window period.
            price_column: Column name for price data.
            signal_column: Column name for output signal.
            reason_column: Column name for signal reason.
        """
        if fast_window >= slow_window:
            raise ValueError("fast_window must be less than slow_window")
        if fast_window < 1 or slow_window < 1:
            raise ValueError("Window values must be positive")

        self.fast_window = fast_window
        self.slow_window = slow_window
        self.price_column = price_column
        self.signal_column = signal_column
        self.reason_column = reason_column
        self.strategy_name = "trend_following"

    def generate_signal(self, data: pd.DataFrame) -> pd.Series:
        """Generate trend following signals from OHLCV data.

        Args:
            data: DataFrame with price data. Must contain price_column.

        Returns:
            Series with signal values: 1 for LONG, 0 for FLAT.
        """
        if self.price_column not in data.columns:
            raise ValueError(f"Missing required column: {self.price_column}")

        df = data.copy()
        df[f"ma_fast_{self.fast_window}"] = df[self.price_column].rolling(window=self.fast_window).mean()
        df[f"ma_slow_{self.slow_window}"] = df[self.price_column].rolling(window=self.slow_window).mean()

        fast_col = f"ma_fast_{self.fast_window}"
        slow_col = f"ma_slow_{self.slow_window}"

        signals = pd.Series(0, index=df.index, dtype=int)
        signals[df[fast_col] > df[slow_col]] = 1

        df[self.signal_column] = signals
        df[self.reason_column] = signals.apply(
            lambda x: "fast_ma_crossed_above_slow_ma" if x == 1 else "fast_ma_below_slow_ma"
        )

        return signals

    def get_params(self) -> dict:
        """Get strategy parameters as dictionary."""
        return {
            "fast_window": self.fast_window,
            "slow_window": self.slow_window,
            "price_column": self.price_column,
            "strategy_name": self.strategy_name,
        }

    def __repr__(self) -> str:
        return f"TrendFollowingStrategy(fast_window={self.fast_window}, slow_window={self.slow_window})"