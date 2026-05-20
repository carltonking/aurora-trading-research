"""Tests for ensemble strategy."""

import pandas as pd
import pytest
from unittest.mock import MagicMock

from aurora.strategies.ensemble import EnsembleStrategy


def create_sample_data(periods: int = 50) -> pd.DataFrame:
    """Create sample OHLCV data for testing."""
    dates = pd.date_range(start="2020-01-01", periods=periods, freq="D")
    return pd.DataFrame({
        "close": 100 + pd.Series(range(periods)) * 0.5,
        "open": 99 + pd.Series(range(periods)) * 0.5,
        "high": 102 + pd.Series(range(periods)) * 0.5,
        "low": 98 + pd.Series(range(periods)) * 0.5,
        "volume": 1000000,
    }, index=dates)


class MockStrategy:
    """Mock strategy for testing ensemble."""

    def __init__(self, signals: list[int]) -> None:
        self._signals = signals
        self.strategy_name = "mock"

    def generate_signal(self, data: pd.DataFrame) -> pd.Series:
        return pd.Series(self._signals[:len(data)], index=data.index)


def test_ensemble_initialization() -> None:
    """Test ensemble initializes correctly."""
    strategies = [(MockStrategy([1, 0, -1]), 1.0)]
    ensemble = EnsembleStrategy(strategies, method="vote")

    assert ensemble.method == "vote"
    assert len(ensemble.strategies) == 1


def test_ensemble_invalid_method() -> None:
    """Test ensemble rejects invalid method."""
    strategies = [(MockStrategy([1]), 1.0)]
    with pytest.raises(ValueError):
        EnsembleStrategy(strategies, method="invalid")


def test_ensemble_empty_strategies() -> None:
    """Test ensemble rejects empty strategies."""
    with pytest.raises(ValueError):
        EnsembleStrategy([], method="vote")


def test_ensemble_zero_weight() -> None:
    """Test ensemble rejects zero total weight."""
    strategies = [(MockStrategy([1]), 0.0)]
    with pytest.raises(ValueError):
        EnsembleStrategy(strategies, method="vote")


def test_ensemble_vote_signal() -> None:
    """Test ensemble vote method."""
    s1 = MockStrategy([1, 1, 1, 0, -1])
    s2 = MockStrategy([1, 0, -1, -1, -1])
    s3 = MockStrategy([1, 1, 0, 0, 0])

    strategies = [(s1, 1.0), (s2, 1.0), (s3, 1.0)]
    ensemble = EnsembleStrategy(strategies, method="vote")

    data = create_sample_data(5)
    signals = ensemble.generate_signal(data)

    assert len(signals) == 5
    assert set(signals.unique()).issubset({-1, 0, 1})


def test_ensemble_weighted_signal() -> None:
    """Test ensemble weighted method."""
    s1 = MockStrategy([1, 1, 1, 1, 1])
    s2 = MockStrategy([-1, -1, -1, -1, -1])

    strategies = [(s1, 0.6), (s2, 0.4)]
    ensemble = EnsembleStrategy(strategies, method="weighted", weighted_threshold=0.2)

    data = create_sample_data(5)
    signals = ensemble.generate_signal(data)

    assert len(signals) == 5


def test_ensemble_unanimous_signal() -> None:
    """Test ensemble unanimous method."""
    s1 = MockStrategy([1, 1, 0, -1, -1])
    s2 = MockStrategy([1, 1, 0, -1, -1])
    s3 = MockStrategy([1, 1, 0, -1, -1])

    strategies = [(s1, 1.0), (s2, 1.0), (s3, 1.0)]
    ensemble = EnsembleStrategy(strategies, method="unanimous")

    data = create_sample_data(5)
    signals = ensemble.generate_signal(data)

    assert int(signals.iloc[0]) == 1
    assert int(signals.iloc[1]) == 1
    assert int(signals.iloc[4]) == -1


def test_ensemble_single_strategy() -> None:
    """Test ensemble with single strategy behaves like that strategy."""
    s1 = MockStrategy([1, 0, -1, 1, 0])

    strategies = [(s1, 1.0)]
    ensemble = EnsembleStrategy(strategies, method="vote")

    data = create_sample_data(5)
    signals = ensemble.generate_signal(data)

    assert [int(x) for x in signals] == [1, 0, -1, 1, 0]


def test_ensemble_parameters_property() -> None:
    """Test ensemble parameters property."""
    s1 = MockStrategy([1])
    s2 = MockStrategy([0])

    strategies = [(s1, 0.7), (s2, 0.3)]
    ensemble = EnsembleStrategy(strategies, method="weighted")

    params = ensemble.parameters

    assert params["method"] == "weighted"
    assert len(params["sub_strategies"]) == 2


def test_ensemble_repr() -> None:
    """Test ensemble __repr__."""
    s1 = MockStrategy([1])

    strategies = [(s1, 1.0)]
    ensemble = EnsembleStrategy(strategies, method="vote")

    repr_str = repr(ensemble)
    assert "vote" in repr_str


def test_ensemble_normalize_signal() -> None:
    """Test signal normalization."""
    s1 = MagicMock()
    s1.generate_signal.return_value = pd.Series([0.5, -0.3, 0.0, 1.0, -1.0])

    strategies = [(s1, 1.0)]
    ensemble = EnsembleStrategy(strategies, method="vote")

    data = create_sample_data(5)
    signals = ensemble.generate_signal(data)

    assert set(signals.unique()).issubset({-1, 0, 1})


def test_ensemble_builder_integration() -> None:
    """Test ensemble built from config."""
    from aurora.strategies.builder import StrategyBuilder

    config = {
        "strategy_name": "test_ensemble",
        "archetype": "ensemble",
        "parameters": {
            "method": "vote",
            "strategies": [
                {
                    "archetype": "trend_following",
                    "parameters": {"fast_window": 5, "slow_window": 15},
                    "weight": 0.6,
                },
                {
                    "archetype": "breakout",
                    "parameters": {"lookback_period": 20},
                    "weight": 0.4,
                },
            ],
        },
    }

    builder = StrategyBuilder(config)
    strategy = builder.build()

    assert isinstance(strategy, EnsembleStrategy)
    assert strategy.strategy_name == "test_ensemble"
    assert strategy.method == "vote"
    assert len(strategy.strategies) == 2