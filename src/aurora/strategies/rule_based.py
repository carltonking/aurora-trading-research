"""Simple deterministic rule-based research strategies."""

import pandas as pd

from aurora.strategies.base import SignalResult, Strategy
from aurora.strategies.exceptions import SignalGenerationError
from aurora.strategies.signals import (
    SIGNAL_COLUMN,
    SIGNAL_LONG,
    SIGNAL_REASON_COLUMN,
    empty_signal_frame,
    summarize_signals,
)


class MovingAverageCrossoverStrategy(Strategy):
    """Long when a fast moving average is above a slow moving average."""

    def generate_signals(self, df: pd.DataFrame) -> tuple[pd.DataFrame, SignalResult]:
        """Generate moving-average crossover signals."""
        output = empty_signal_frame(df, self.config.strategy_id)
        if self.config.direction == "flat_only":
            output[SIGNAL_REASON_COLUMN] = "flat_only"
            return output, summarize_signals(output, self.config.strategy_id)

        rule = self.config.entry_rules[0] if self.config.entry_rules else {}
        fast_ma = rule.get("fast_ma")
        slow_ma = rule.get("slow_ma")
        if not fast_ma or not slow_ma:
            raise SignalGenerationError("Moving average crossover requires fast_ma and slow_ma.")
        _require_columns(output, [str(fast_ma), str(slow_ma)])

        long_mask = output[str(fast_ma)] > output[str(slow_ma)]
        output.loc[long_mask, SIGNAL_COLUMN] = SIGNAL_LONG
        output.loc[long_mask, SIGNAL_REASON_COLUMN] = "fast_ma_above_slow_ma"
        output.loc[~long_mask, SIGNAL_REASON_COLUMN] = "fast_ma_not_above_slow_ma"
        return output, summarize_signals(output, self.config.strategy_id)


class MomentumStrategy(Strategy):
    """Long when a configured return column exceeds a threshold."""

    def generate_signals(self, df: pd.DataFrame) -> tuple[pd.DataFrame, SignalResult]:
        """Generate momentum threshold signals."""
        output = empty_signal_frame(df, self.config.strategy_id)
        if self.config.direction == "flat_only":
            output[SIGNAL_REASON_COLUMN] = "flat_only"
            return output, summarize_signals(output, self.config.strategy_id)

        rule = self.config.entry_rules[0] if self.config.entry_rules else {}
        return_col = rule.get("return_col")
        min_return = float(rule.get("min_return", 0.0))
        if not return_col:
            raise SignalGenerationError("Momentum strategy requires return_col.")
        _require_columns(output, [str(return_col)])

        long_mask = output[str(return_col)] >= min_return
        output.loc[long_mask, SIGNAL_COLUMN] = SIGNAL_LONG
        output.loc[long_mask, SIGNAL_REASON_COLUMN] = "return_above_threshold"
        output.loc[~long_mask, SIGNAL_REASON_COLUMN] = "return_below_threshold"
        return output, summarize_signals(output, self.config.strategy_id)


def _require_columns(df: pd.DataFrame, columns: list[str]) -> None:
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise SignalGenerationError(f"Missing required columns: {', '.join(missing)}")
