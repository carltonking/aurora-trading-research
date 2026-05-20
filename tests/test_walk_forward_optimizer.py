"""Tests for walk-forward optimizer."""

import pandas as pd
import pytest
from unittest.mock import MagicMock, patch

from aurora.optimization.walk_forward_optimizer import (
    WalkForwardOptimizer,
    WalkForwardOptimizerConfig,
    WindowResult,
    WalkForwardResult,
)


def create_sample_data(periods: int = 200) -> pd.DataFrame:
    """Create sample OHLCV data."""
    dates = pd.date_range(start="2020-01-01", periods=periods, freq="D")
    return pd.DataFrame({
        "open": 100 + pd.Series(range(periods)) * 0.5,
        "high": 102 + pd.Series(range(periods)) * 0.5,
        "low": 98 + pd.Series(range(periods)) * 0.5,
        "close": 100 + pd.Series(range(periods)) * 0.5,
        "volume": 1000000,
    }, index=dates)


class TestWalkForwardOptimizerConfig:
    """Tests for WalkForwardOptimizerConfig."""

    def test_default_config(self) -> None:
        """Test config with default values."""
        config = WalkForwardOptimizerConfig(
            strategy_archetype="trend_following",
            param_space={"fast_window": {"type": "int", "low": 5, "high": 20}},
        )
        assert config.strategy_archetype == "trend_following"
        assert config.train_ratio == 0.6
        assert config.anchor is True
        assert config.reoptimize_freq == "monthly"

    def test_custom_config(self) -> None:
        """Test config with custom values."""
        config = WalkForwardOptimizerConfig(
            strategy_archetype="breakout",
            param_space={},
            train_ratio=0.7,
            anchor=False,
            purge_days=10,
            embargo_days=5,
            reoptimize_freq="quarterly",
        )
        assert config.train_ratio == 0.7
        assert config.anchor is False
        assert config.purge_days == 10
        assert config.reoptimize_freq == "quarterly"


class TestWalkForwardOptimizer:
    """Tests for WalkForwardOptimizer."""

    def test_initialization(self) -> None:
        """Test optimizer initializes correctly."""
        config = WalkForwardOptimizerConfig(
            strategy_archetype="trend_following",
            param_space={},
        )

        def builder(params):
            return MagicMock()

        def fetcher(sym, start, end):
            return create_sample_data()

        optimizer = WalkForwardOptimizer(config, builder, fetcher)

        assert optimizer.config == config

    def test_create_windows_anchored(self) -> None:
        """Test anchored window creation."""
        config = WalkForwardOptimizerConfig(
            strategy_archetype="trend_following",
            param_space={},
            anchor=True,
            train_ratio=0.6,
        )

        optimizer = WalkForwardOptimizer(config, lambda p: None, lambda s, s2, e: create_sample_data())

        data = create_sample_data(200)
        windows = optimizer._create_windows(data, "2020-01-01", "2024-01-01")

        assert len(windows) > 0
        train_start, train_end, test_start, test_end = windows[0]
        assert train_start == "2020-01-01"

    def test_create_windows_rolling(self) -> None:
        """Test rolling window creation."""
        config = WalkForwardOptimizerConfig(
            strategy_archetype="trend_following",
            param_space={},
            anchor=False,
            train_ratio=0.6,
        )

        optimizer = WalkForwardOptimizer(config, lambda p: None, lambda s, s2, e: create_sample_data())

        data = create_sample_data(200)
        windows = optimizer._create_windows(data, "2020-01-01", "2024-01-01")

        assert len(windows) > 0

    def test_run_with_mock_optimizer(self) -> None:
        """Test run method with mocked inner optimizer."""
        config = WalkForwardOptimizerConfig(
            strategy_archetype="trend_following",
            param_space={"fast_window": {"type": "int", "low": 5, "high": 10}},
            train_ratio=0.5,
            anchor=True,
            reoptimize_freq="monthly",
            inner_optimizer="genetic",
        )

        def builder(params):
            mock_strategy = MagicMock()
            mock_signal = pd.Series(0, index=range(100))
            mock_signal.iloc[10:20] = 1
            mock_strategy.generate_signal.return_value = mock_signal
            return mock_strategy

        def fetcher(sym, start, end):
            return create_sample_data(365)

        with patch("aurora.optimization.advanced.genetic.GeneticOptimizer") as mock_ga:
            mock_result = MagicMock()
            mock_result.parameters = {"fast_window": 8}
            mock_result.fitness = 1.5
            mock_ga.return_value.optimize.return_value = mock_result

            optimizer = WalkForwardOptimizer(config, builder, fetcher)
            result = optimizer.run("AAPL", "2020-01-01", "2024-01-01")

            assert isinstance(result, WalkForwardResult)
            assert isinstance(result.overall_oos_metrics, dict)

    def test_backtest_on_data(self) -> None:
        """Test backtest on data method."""
        config = WalkForwardOptimizerConfig(
            strategy_archetype="trend_following",
            param_space={},
        )

        optimizer = WalkForwardOptimizer(config, lambda p: None, lambda s, s2, e: create_sample_data())

        data = create_sample_data(50)

        class MockStrategy:
            def __init__(self):
                self.strategy_name = "test"
            def generate_signal(self, data):
                return pd.Series([1, 0, 1, 0, 1] * 10, index=data.index)

        metrics = optimizer._backtest_on_data({"fast_window": 10}, data)

        assert "sharpe_ratio" in metrics
        assert "total_return" in metrics
        assert "trades" in metrics


def test_window_result_to_dict() -> None:
    """Test WindowResult serialization."""
    window = WindowResult(
        train_start="2020-01-01",
        train_end="2021-01-01",
        test_start="2021-01-02",
        test_end="2021-02-01",
        best_params={"fast_window": 10},
        train_metric=1.5,
        oos_metric=1.2,
        trades=10,
        oos_return=0.05,
    )

    result = WalkForwardResult(
        windows=[window],
        overall_oos_metrics={"sharpe_ratio": 1.2},
    )

    result_dict = result.to_dict()

    assert "windows" in result_dict
    assert "overall_oos_metrics" in result_dict
    assert len(result_dict["windows"]) == 1