"""Tests for strategy builder."""

import json
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from aurora.strategies.builder import StrategyBuilder, StrategyBuilderError


def create_temp_config(temp_dir: Path, config: dict, suffix: str = ".json") -> Path:
    """Create a temporary config file."""
    config_path = temp_dir / f"config{suffix}"
    config_path.write_text(json.dumps(config))
    return config_path


def create_sample_ohlcv_data() -> pd.DataFrame:
    """Create sample OHLCV data for testing."""
    dates = pd.date_range("2024-01-01", periods=50, freq="D")
    data = {
        "open": [100 + i * 0.5 for i in range(50)],
        "high": [105 + i * 0.5 for i in range(50)],
        "low": [95 + i * 0.5 for i in range(50)],
        "close": [100 + i * 0.5 for i in range(50)],
        "volume": [1000000 for _ in range(50)],
    }
    return pd.DataFrame(data, index=dates)


def test_build_trend_following_strategy() -> None:
    """Test building a trend following strategy."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = {
            "strategy_name": "my_ma_cross",
            "archetype": "trend_following",
            "parameters": {
                "fast_window": 10,
                "slow_window": 30,
            },
        }
        config_path = create_temp_config(Path(tmpdir), config)

        builder = StrategyBuilder(config_path=str(config_path))
        builder.load_config()
        strategy = builder.build()

        assert strategy.strategy_name == "my_ma_cross"
        assert strategy.fast_window == 10
        assert strategy.slow_window == 30


def test_build_mean_reversion_strategy() -> None:
    """Test building a mean reversion strategy."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = {
            "strategy_name": "my_mean_reversion",
            "archetype": "mean_reversion",
            "parameters": {
                "window": 20,
                "num_std": 2.0,
                "method": "bollinger",
            },
        }
        config_path = create_temp_config(Path(tmpdir), config)

        builder = StrategyBuilder(config_path=str(config_path))
        builder.load_config()
        strategy = builder.build()

        assert strategy.strategy_name == "my_mean_reversion"
        assert strategy.window == 20
        assert strategy.method == "bollinger"


def test_build_breakout_strategy() -> None:
    """Test building a breakout strategy."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = {
            "strategy_name": "my_breakout",
            "archetype": "breakout",
            "parameters": {
                "lookback_period": 20,
            },
        }
        config_path = create_temp_config(Path(tmpdir), config)

        builder = StrategyBuilder(config_path=str(config_path))
        builder.load_config()
        strategy = builder.build()

        assert strategy.strategy_name == "my_breakout"
        assert strategy.lookback_period == 20


def test_build_invalid_archetype_raises_error() -> None:
    """Test that invalid archetype raises error."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = {
            "strategy_name": "my_strategy",
            "archetype": "invalid_archetype",
            "parameters": {},
        }
        config_path = create_temp_config(Path(tmpdir), config)

        builder = StrategyBuilder(config_path=str(config_path))
        builder.load_config()

        with pytest.raises(StrategyBuilderError, match="Invalid archetype"):
            builder.build()


def test_build_missing_required_field_raises_error() -> None:
    """Test that missing required field raises error."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = {
            "archetype": "trend_following",
            "parameters": {},
        }
        config_path = create_temp_config(Path(tmpdir), config)

        builder = StrategyBuilder(config_path=str(config_path))
        builder.load_config()

        with pytest.raises(StrategyBuilderError, match="Missing required field"):
            builder.build()


def test_build_nonexistent_config_raises_error() -> None:
    """Test that nonexistent config file raises error."""
    builder = StrategyBuilder(config_path="nonexistent/config.json")

    with pytest.raises(StrategyBuilderError, match="Config file not found"):
        builder.load_config()


def test_generated_code_compiles() -> None:
    """Test that generated code can be compiled."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = {
            "strategy_name": "test_strategy",
            "archetype": "trend_following",
            "parameters": {
                "fast_window": 5,
                "slow_window": 15,
            },
        }
        config_path = create_temp_config(Path(tmpdir), config)

        builder = StrategyBuilder(config_path=str(config_path))
        builder.load_config()
        code = builder.generate_code()

        compile(code, "<string>", "exec")


def test_built_strategy_produces_valid_signals() -> None:
    """Test that built strategy produces valid signals."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = {
            "strategy_name": "test_strategy",
            "archetype": "trend_following",
            "parameters": {
                "fast_window": 5,
                "slow_window": 10,
            },
        }
        config_path = create_temp_config(Path(tmpdir), config)

        builder = StrategyBuilder(config_path=str(config_path))
        builder.load_config()
        strategy = builder.build()

        data = create_sample_ohlcv_data()
        signals = strategy.generate_signal(data)

        assert len(signals) == len(data)
        assert set(signals.unique()).issubset({0, 1})


def test_mean_reversion_rsi_signals() -> None:
    """Test mean reversion strategy with RSI method."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = {
            "strategy_name": "rsi_strategy",
            "archetype": "mean_reversion",
            "parameters": {
                "method": "rsi",
                "rsi_period": 14,
                "rsi_oversold": 30,
                "rsi_overbought": 70,
            },
        }
        config_path = create_temp_config(Path(tmpdir), config)

        builder = StrategyBuilder(config_path=str(config_path))
        builder.load_config()
        strategy = builder.build()

        data = create_sample_ohlcv_data()
        signals = strategy.generate_signal(data)

        assert len(signals) == len(data)


def test_breakout_strategy_signals() -> None:
    """Test breakout strategy produces valid signals."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = {
            "strategy_name": "breakout_strategy",
            "archetype": "breakout",
            "parameters": {
                "lookback_period": 10,
            },
        }
        config_path = create_temp_config(Path(tmpdir), config)

        builder = StrategyBuilder(config_path=str(config_path))
        builder.load_config()
        strategy = builder.build()

        data = create_sample_ohlcv_data()
        signals = strategy.generate_signal(data)

        assert len(signals) == len(data)
        assert set(signals.unique()).issubset({0, 1})


def test_invalid_parameters_raise_error() -> None:
    """Test that invalid parameters raise error."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = {
            "strategy_name": "test",
            "archetype": "trend_following",
            "parameters": {
                "fast_window": 30,
                "slow_window": 10,
            },
        }
        config_path = create_temp_config(Path(tmpdir), config)

        builder = StrategyBuilder(config_path=str(config_path))
        builder.load_config()

        with pytest.raises(StrategyBuilderError, match="fast_window must be less than slow_window"):
            builder.build()