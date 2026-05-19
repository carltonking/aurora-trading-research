"""Mean reversion strategy archetype using Bollinger Bands or RSI.

This is a research-only signal generator. No live trading, no broker calls.
"""

import pandas as pd


class MeanReversionStrategy:
    """Mean reversion strategy using Bollinger Bands.

    Generates LONG signals when price is below lower Bollinger Band.
    Generates FLAT signals when price is above middle band or above upper band.
    """

    def __init__(
        self,
        window: int = 20,
        num_std: float = 2.0,
        price_column: str = "close",
        signal_column: str = "signal",
        reason_column: str = "reason",
        method: str = "bollinger",
        rsi_period: int = 14,
        rsi_oversold: float = 30,
        rsi_overbought: float = 70,
    ):
        """Initialize mean reversion strategy with parameters.

        Args:
            window: Rolling window for Bollinger Bands calculation.
            num_std: Number of standard deviations for bands.
            price_column: Column name for price data.
            signal_column: Column name for output signal.
            reason_column: Column name for signal reason.
            method: "bollinger" or "rsi".
            rsi_period: RSI period (used if method="rsi").
            rsi_oversold: RSI oversold threshold (used if method="rsi").
            rsi_overbought: RSI overbought threshold (used if method="rsi").
        """
        if window < 1:
            raise ValueError("Window must be positive")
        if num_std <= 0:
            raise ValueError("num_std must be positive")
        if method not in ("bollinger", "rsi"):
            raise ValueError("method must be 'bollinger' or 'rsi'")

        self.window = window
        self.num_std = num_std
        self.price_column = price_column
        self.signal_column = signal_column
        self.reason_column = reason_column
        self.method = method
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.strategy_name = "mean_reversion"

    def _calculate_rsi(self, series: pd.Series, period: int) -> pd.Series:
        """Calculate RSI indicator."""
        delta = series.diff()
        gain = delta.where(delta > 0, 0)
        loss = (-delta).where(delta < 0, 0)

        avg_gain = gain.rolling(window=period, min_periods=1).mean()
        avg_loss = loss.rolling(window=period, min_periods=1).mean()

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def generate_signal(self, data: pd.DataFrame) -> pd.Series:
        """Generate mean reversion signals from OHLCV data.

        Args:
            data: DataFrame with price data. Must contain price_column.

        Returns:
            Series with signal values: 1 for LONG, 0 for FLAT.
        """
        if self.price_column not in data.columns:
            raise ValueError(f"Missing required column: {self.price_column}")

        df = data.copy()

        if self.method == "bollinger":
            rolling_mean = df[self.price_column].rolling(window=self.window).mean()
            rolling_std = df[self.price_column].rolling(window=self.window).std()

            lower_band = rolling_mean - (self.num_std * rolling_std)
            upper_band = rolling_mean + (self.num_std * rolling_std)

            signals = pd.Series(0, index=df.index, dtype=int)
            signals[df[self.price_column] < lower_band] = 1

            df[self.reason_column] = signals.apply(
                lambda x: "price_below_lower_band" if x == 1 else "price_not_below_lower_band"
            )

        elif self.method == "rsi":
            rsi = self._calculate_rsi(df[self.price_column], self.rsi_period)

            signals = pd.Series(0, index=df.index, dtype=int)
            signals[rsi < self.rsi_oversold] = 1

            df[self.reason_column] = signals.apply(
                lambda x: "rsi_oversold" if x == 1 else "rsi_not_oversold"
            )

        df[self.signal_column] = signals
        return signals

    def get_params(self) -> dict:
        """Get strategy parameters as dictionary."""
        params = {
            "window": self.window,
            "num_std": self.num_std,
            "price_column": self.price_column,
            "method": self.method,
            "strategy_name": self.strategy_name,
        }
        if self.method == "rsi":
            params.update({
                "rsi_period": self.rsi_period,
                "rsi_oversold": self.rsi_oversold,
                "rsi_overbought": self.rsi_overbought,
            })
        return params

    def __repr__(self) -> str:
        return f"MeanReversionStrategy(window={self.window}, method={self.method})"