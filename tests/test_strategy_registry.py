import pytest

from aurora.strategies.config import strategy_config_from_dict
from aurora.strategies.exceptions import StrategyRegistryError
from aurora.strategies.ml_signal import MLSignalStrategy
from aurora.strategies.registry import (
    instantiate_strategy,
    list_strategies,
    load_strategy_from_registry,
    save_strategy_config,
)
from aurora.strategies.rule_based import MomentumStrategy, MovingAverageCrossoverStrategy
from tests.test_strategy_config import valid_strategy_dict


def test_save_load_strategy_config(tmp_path) -> None:
    config = strategy_config_from_dict(valid_strategy_dict())

    path = save_strategy_config(config, base_dir=tmp_path)
    loaded = load_strategy_from_registry(config.strategy_id, base_dir=tmp_path)

    assert path.exists()
    assert (path / "config.yaml").exists()
    assert (path / "metadata.json").exists()
    assert loaded == config


def test_list_strategies_returns_metadata(tmp_path) -> None:
    config = strategy_config_from_dict(valid_strategy_dict())
    save_strategy_config(config, base_dir=tmp_path)

    result = list_strategies(base_dir=tmp_path)

    assert len(result) == 1
    assert result[0]["strategy_id"] == config.strategy_id
    assert result[0]["status"] == "draft"


def test_instantiate_supported_strategies() -> None:
    assert isinstance(
        instantiate_strategy(strategy_config_from_dict(valid_strategy_dict("ml_signal"))),
        MLSignalStrategy,
    )
    assert isinstance(
        instantiate_strategy(strategy_config_from_dict(valid_strategy_dict("moving_average_crossover"))),
        MovingAverageCrossoverStrategy,
    )
    assert isinstance(
        instantiate_strategy(strategy_config_from_dict(valid_strategy_dict("momentum"))),
        MomentumStrategy,
    )


def test_unsupported_allowed_strategy_raises() -> None:
    config = strategy_config_from_dict(valid_strategy_dict("mean_reversion"))

    with pytest.raises(StrategyRegistryError):
        instantiate_strategy(config)
