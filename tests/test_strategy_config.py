import pytest

from aurora.strategies.config import strategy_config_from_dict, validate_strategy_config
from aurora.strategies.exceptions import StrategyConfigError


def valid_strategy_dict(strategy_type: str = "ml_signal") -> dict:
    entry_rules = {
        "ml_signal": [
            {
                "prediction_col": "prediction",
                "probability_col": "prediction_probability",
                "min_probability": 0.55,
            }
        ],
        "moving_average_crossover": [{"fast_ma": "ma_20", "slow_ma": "ma_50"}],
        "momentum": [{"return_col": "return_20d", "min_return": 0.03}],
        "mean_reversion": [],
        "breakout": [],
    }
    return {
        "strategy_id": f"{strategy_type}_test",
        "name": f"{strategy_type} test",
        "strategy_type": strategy_type,
        "asset_class": "equity",
        "universe": {"symbols": ["AAPL"]},
        "timeframe": "1d",
        "direction": "long_only",
        "entry_rules": entry_rules[strategy_type],
        "exit_rules": [],
        "risk": {
            "max_position_pct": 0.05,
            "allow_shorting": False,
            "allow_margin": False,
        },
        "validation": {"require_walk_forward": True},
    }


def test_valid_config_dict_converts_and_validates() -> None:
    config = strategy_config_from_dict(valid_strategy_dict())

    validate_strategy_config(config)
    assert config.strategy_id == "ml_signal_test"
    assert config.direction == "long_only"


def test_invalid_strategy_type_raises() -> None:
    data = valid_strategy_dict()
    data["strategy_type"] = "live_trader"

    with pytest.raises(StrategyConfigError):
        strategy_config_from_dict(data)


def test_shorting_or_margin_enabled_raises() -> None:
    shorting = valid_strategy_dict()
    shorting["risk"]["allow_shorting"] = True
    with pytest.raises(StrategyConfigError):
        strategy_config_from_dict(shorting)

    margin = valid_strategy_dict()
    margin["risk"]["allow_margin"] = True
    with pytest.raises(StrategyConfigError):
        strategy_config_from_dict(margin)


def test_max_position_pct_above_limit_raises() -> None:
    data = valid_strategy_dict()
    data["risk"]["max_position_pct"] = 0.15

    with pytest.raises(StrategyConfigError):
        strategy_config_from_dict(data)
