"""ML prediction based signal strategy."""

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


class MLSignalStrategy(Strategy):
    """Generate long/flat signals from model predictions."""

    def generate_signals(self, df: pd.DataFrame) -> tuple[pd.DataFrame, SignalResult]:
        """Generate signals from prediction columns."""
        output = empty_signal_frame(df, self.config.strategy_id)
        if self.config.direction == "flat_only":
            output[SIGNAL_REASON_COLUMN] = "flat_only"
            return output, summarize_signals(output, self.config.strategy_id)

        rule = self.config.entry_rules[0] if self.config.entry_rules else {}
        prediction_col = str(rule.get("prediction_col", "prediction"))
        probability_col = str(rule.get("probability_col", "prediction_probability"))
        min_probability = float(rule.get("min_probability", 0.55))

        if prediction_col not in output.columns:
            raise SignalGenerationError(f"Missing prediction column: {prediction_col}")

        positive = output[prediction_col] == 1
        if probability_col in output.columns:
            above_threshold = output[probability_col] >= min_probability
            output.loc[positive & above_threshold, SIGNAL_COLUMN] = SIGNAL_LONG
            output.loc[positive & above_threshold, SIGNAL_REASON_COLUMN] = "model_positive"
            output.loc[positive & ~above_threshold, SIGNAL_REASON_COLUMN] = (
                "below_probability_threshold"
            )
        else:
            output.loc[positive, SIGNAL_COLUMN] = SIGNAL_LONG
            output.loc[positive, SIGNAL_REASON_COLUMN] = "model_positive"

        output.loc[~positive, SIGNAL_REASON_COLUMN] = "model_flat"
        return output, summarize_signals(output, self.config.strategy_id)
