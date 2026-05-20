"""Pairs trading strategy archetype.

This is a research-only signal generator. No live trading, no broker calls.
"""

import pandas as pd


class PairsTradingStrategy:
    """Pairs trading strategy - trade spread between two related securities.

    Generates LONG signals when spread is cheap (z-score < -entry_z).
    Generates SHORT signals when spread is expensive (z-score > entry_z).
    Generates FLAT signals when spread reverts (within exit_z).
    """

    def __init__(
        self,
        symbol_a: str = "SPY",
        symbol_b: str = "SH",
        lookback: int = 60,
        entry_z: float = 2.0,
        exit_z: float = 0.5,
        price_column: str = "close",
        signal_column: str = "signal",
        reason_column: str = "reason",
    ):
        """Initialize pairs trading strategy with parameters.

        Args:
            symbol_a: First symbol in the pair.
            symbol_b: Second symbol in the pair.
            lookback: Rolling window for z-score calculation.
            entry_z: Z-score threshold for entry (signal at extremes).
            exit_z: Z-score threshold for exit (back to mean).
            price_column: Column name for price data.
            signal_column: Column name for output signal.
            reason_column: Column name for signal reason.
        """
        if lookback < 2:
            raise ValueError("lookback must be at least 2")
        if entry_z <= exit_z:
            raise ValueError("entry_z must be greater than exit_z")

        self.symbol_a = symbol_a
        self.symbol_b = symbol_b
        self.lookback = lookback
        self.entry_z = entry_z
        self.exit_z = exit_z
        self.price_column = price_column
        self.signal_column = signal_column
        self.reason_column = reason_column
        self.strategy_name = "pairs_trading"

    def __repr__(self) -> str:
        return (
            f"PairsTradingStrategy(symbol_a={self.symbol_a}, symbol_b={self.symbol_b}, "
            f"lookback={self.lookback}, entry_z={self.entry_z}, exit_z={self.exit_z})"
        )

    def generate_signal(self, data: pd.DataFrame) -> pd.Series:
        """Generate pairs trading signals from dual price data.

        Args:
            data: DataFrame with price data for both symbols. Should have
                  columns like 'symbol_a_close' and 'symbol_b_close' or
                  multi-index with both symbols.

        Returns:
            Series with signals: 1 for long spread, -1 for short spread, 0 for flat.
        """
        col_a = f"{self.symbol_a.lower()}_close"
        col_b = f"{self.symbol_b.lower()}_close"

        if col_a not in data.columns or col_b not in data.columns:
            if len(data.columns) >= 2:
                close_a = data.iloc[:, 0]
                close_b = data.iloc[:, 1]
            else:
                raise ValueError(f"Data must contain price columns for both symbols")
        else:
            close_a = data[col_a]
            close_b = data[col_b]

        spread = close_a / close_b
        rolling_mean = spread.rolling(window=self.lookback).mean()
        rolling_std = spread.rolling(window=self.lookback).std()
        z_score = (spread - rolling_mean) / rolling_std

        signals = pd.Series(0, index=data.index)
        reasons = pd.Series("", index=data.index)

        position = 0
        for i in range(self.lookback, len(z_score)):
            z = z_score.iloc[i]
            if pd.isna(z):
                continue

            if position == 0:
                if z < -self.entry_z:
                    signals.iloc[i] = 1
                    reasons.iloc[i] = f"spread_cheap_z={z:.2f}"
                    position = 1
                elif z > self.entry_z:
                    signals.iloc[i] = -1
                    reasons.iloc[i] = f"spread_expensive_z={z:.2f}"
                    position = -1
            elif position == 1:
                if z > -self.exit_z:
                    signals.iloc[i] = 0
                    reasons.iloc[i] = f"spread_reverted_z={z:.2f}"
                    position = 0
            elif position == -1:
                if z < self.exit_z:
                    signals.iloc[i] = 0
                    reasons.iloc[i] = f"spread_reverted_z={z:.2f}"
                    position = 0

        result = data.copy()
        result[self.signal_column] = signals
        result[self.reason_column] = reasons
        return result[self.signal_column]