import pandas as pd
import pytest

from aurora.strategies.config import strategy_config_from_dict
from aurora.strategies.exceptions import SignalGenerationError
from aurora.strategies.rule_based import MomentumStrategy, MovingAverageCrossoverStrategy
from aurora.strategies.signals import SIGNAL_COLUMN
from tests.test_strategy_config import valid_strategy_dict


def test_moving_average_crossover_generates_expected_signals() -> None:
    strategy = MovingAverageCrossoverStrategy(
        strategy_config_from_dict(valid_strategy_dict("moving_average_crossover"))
    )
    df = pd.DataFrame({"ma_20": [10.0, 12.0, 9.0], "ma_50": [11.0, 11.0, 9.0]})

    result_df, result = strategy.generate_signals(df)

    assert result_df[SIGNAL_COLUMN].tolist() == [0, 1, 0]
    assert result.long_count == 1


def test_momentum_generates_expected_signals() -> None:
    strategy = MomentumStrategy(strategy_config_from_dict(valid_strategy_dict("momentum")))
    df = pd.DataFrame({"return_20d": [0.01, 0.03, 0.05]})

    result_df, result = strategy.generate_signals(df)

    assert result_df[SIGNAL_COLUMN].tolist() == [0, 1, 1]
    assert result.long_count == 2


def test_rule_based_missing_required_columns_raise() -> None:
    ma_strategy = MovingAverageCrossoverStrategy(
        strategy_config_from_dict(valid_strategy_dict("moving_average_crossover"))
    )
    with pytest.raises(SignalGenerationError):
        ma_strategy.generate_signals(pd.DataFrame({"ma_20": [10.0]}))

    momentum_strategy = MomentumStrategy(strategy_config_from_dict(valid_strategy_dict("momentum")))
    with pytest.raises(SignalGenerationError):
        momentum_strategy.generate_signals(pd.DataFrame({"return_5d": [0.05]}))
