import pandas as pd
import pytest

from aurora.strategies.config import strategy_config_from_dict
from aurora.strategies.exceptions import SignalGenerationError
from aurora.strategies.ml_signal import MLSignalStrategy
from aurora.strategies.signals import SIGNAL_COLUMN, SIGNAL_REASON_COLUMN
from tests.test_strategy_config import valid_strategy_dict


def test_ml_signal_generates_long_above_threshold_and_flat_below() -> None:
    config = strategy_config_from_dict(valid_strategy_dict("ml_signal"))
    strategy = MLSignalStrategy(config)
    df = pd.DataFrame(
        {
            "prediction": [1, 1, 0],
            "prediction_probability": [0.60, 0.50, 0.90],
        }
    )

    result_df, result = strategy.generate_signals(df)

    assert result_df[SIGNAL_COLUMN].tolist() == [1, 0, 0]
    assert result_df[SIGNAL_REASON_COLUMN].tolist() == [
        "model_positive",
        "below_probability_threshold",
        "model_flat",
    ]
    assert result.long_count == 1
    assert result.flat_count == 2


def test_ml_signal_missing_prediction_column_raises() -> None:
    config = strategy_config_from_dict(valid_strategy_dict("ml_signal"))
    strategy = MLSignalStrategy(config)

    with pytest.raises(SignalGenerationError):
        strategy.generate_signals(pd.DataFrame({"prediction_probability": [0.60]}))
