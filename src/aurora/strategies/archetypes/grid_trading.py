"""Grid trading strategy archetype.

This is a research-only signal generator. No live trading, no broker calls.
"""

import pandas as pd


class GridTradingStrategy:
    """Grid trading strategy - buy low, sell high within grid bands.

    Generates LONG signals when price enters a buy zone (below a grid level).
    Generates FLAT signals otherwise.
    """

    def __init__(
        self,
        grid_spacing_pct: float = 0.02,
        grid_levels: int = 5,
        price_column: str = "close",
        signal_column: str = "signal",
        reason_column: str = "reason",
    ):
        """Initialize grid trading strategy with parameters.

        Args:
            grid_spacing_pct: Percentage spacing between grid levels (0.02 = 2%).
            grid_levels: Number of grid levels above and below base price.
            price_column: Column name for price data.
            signal_column: Column name for output signal.
            reason_column: Column name for signal reason.
        """
        if not 0 < grid_spacing_pct < 1:
            raise ValueError("grid_spacing_pct must be between 0 and 1")
        if grid_levels < 1:
            raise ValueError("grid_levels must be positive")

        self.grid_spacing_pct = grid_spacing_pct
        self.grid_levels = grid_levels
        self.price_column = price_column
        self.signal_column = signal_column
        self.reason_column = reason_column
        self.strategy_name = "grid_trading"
        self._grid_levels: list[float] = []

    def __repr__(self) -> str:
        return (
            f"GridTradingStrategy(grid_spacing_pct={self.grid_spacing_pct}, "
            f"grid_levels={self.grid_levels})"
        )

    def generate_signal(self, data: pd.DataFrame) -> pd.Series:
        """Generate grid trading signals from OHLCV data.

        Args:
            data: DataFrame with price data. Must contain price_column.

        Returns:
            Series with signals: 1 for buy zones, 0 for hold.
        """
        if self.price_column not in data.columns:
            raise ValueError(f"Price column '{self.price_column}' not found in data")

        prices = data[self.price_column]
        signals = pd.Series(0, index=data.index)
        reasons = pd.Series("", index=data.index)

        base_price = prices.iloc[0]
        self._grid_levels = []
        for i in range(1, self.grid_levels + 1):
            self._grid_levels.append(base_price * (1 - i * self.grid_spacing_pct))
            self._grid_levels.append(base_price * (1 + i * self.grid_spacing_pct))
        self._grid_levels.sort()

        for i, price in enumerate(prices):
            for level in self._grid_levels:
                if price <= level * (1 - self.grid_spacing_pct / 2):
                    signals.iloc[i] = 1
                    reasons.iloc[i] = f"price_below_grid_{level:.2f}"
                    break
                elif price >= level * (1 + self.grid_spacing_pct / 2):
                    signals.iloc[i] = 0
                    reasons.iloc[i] = f"price_above_grid_{level:.2f}"

        result = data.copy()
        result[self.signal_column] = signals
        result[self.reason_column] = reasons
        return result[self.signal_column]