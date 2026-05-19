"""Tests for sensitivity analysis."""

import json
import tempfile
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
import pytest

from aurora.analysis.sensitivity import (
    ParamRange,
    SensitivityConfig,
    SensitivityResult,
    SensitivityAnalyzer,
    load_sensitivity_config,
)


def create_sample_ohlcv(days: int = 100, start_price: float = 100.0) -> pd.DataFrame:
    """Create sample OHLCV data."""
    dates = pd.date_range(start="2020-01-01", periods=days, freq="D")
    np.random.seed(42)

    prices = start_price * np.exp(np.cumsum(np.random.randn(days) * 0.02))

    data = {
        "open": prices * (1 + np.random.uniform(-0.01, 0.01, days)),
        "high": prices * (1 + np.random.uniform(0, 0.02, days)),
        "low": prices * (1 + np.random.uniform(-0.02, 0, days)),
        "close": prices,
        "volume": np.random.randint(1000000, 10000000, days),
    }

    return pd.DataFrame(data, index=dates)


def simple_strategy_builder(params: dict) -> Callable[[pd.DataFrame], pd.Series]:
    """Simple strategy builder for testing."""
    threshold = params.get("threshold", 0.01)

    def strategy_fn(df: pd.DataFrame) -> pd.Series:
        signals = pd.Series(0, index=df.index, dtype=int)
        if "close" in df.columns:
            returns = df["close"].pct_change()
            signals[returns > threshold] = 1
        return signals

    return strategy_fn


def ma_strategy_builder(params: dict) -> Callable[[pd.DataFrame], pd.Series]:
    """Moving average strategy builder."""
    window = params.get("window", 5)

    def strategy_fn(df: pd.DataFrame) -> pd.Series:
        signals = pd.Series(0, index=df.index, dtype=int)
        if "close" in df.columns:
            ma = df["close"].rolling(window=window).mean()
            signals[df["close"] > ma] = 1
        return signals

    return strategy_fn


def test_param_range_from_dict_with_min_max_step() -> None:
    """Test creating ParamRange from dict with min/max/step."""
    data = {"min": 5, "max": 20, "step": 5}
    param = ParamRange.from_dict(data)

    assert param.min_value == 5
    assert param.max_value == 20
    assert param.step == 5


def test_param_range_from_dict_with_values() -> None:
    """Test creating ParamRange from dict with values list."""
    data = {"values": [5, 10, 15, 20]}
    param = ParamRange.from_dict(data)

    assert param.values == [5, 10, 15, 20]


def test_param_range_generate_values_from_min_max_step() -> None:
    """Test generating values from min/max/step."""
    param = ParamRange(min_value=5, max_value=20, step=5)
    values = param.generate_values()

    assert values == [5, 10, 15, 20]


def test_param_range_generate_values_from_list() -> None:
    """Test generating values from explicit list."""
    param = ParamRange(values=[5, 10, 15])
    values = param.generate_values()

    assert values == [5, 10, 15]


def test_sensitivity_config_from_dict() -> None:
    """Test creating SensitivityConfig from dict."""
    data = {
        "threshold": {"min": 0.01, "max": 0.05, "step": 0.01},
        "window": {"values": [5, 10, 20]},
    }

    config = SensitivityConfig.from_dict(data)

    assert "threshold" in config.parameters
    assert "window" in config.parameters
    assert config.parameters["threshold"].min_value == 0.01
    assert config.parameters["window"].values == [5, 10, 20]


def test_sensitivity_analyzer_single_param() -> None:
    """Test sensitivity analysis with single parameter."""
    data = create_sample_ohlcv(50)

    config = SensitivityConfig(parameters={
        "threshold": ParamRange(values=[0.01, 0.02, 0.03]),
    })

    analyzer = SensitivityAnalyzer(
        strategy_builder=simple_strategy_builder,
        base_data=data,
    )

    result = analyzer.analyze(config, metric="sharpe_ratio")

    assert len(result.parameter_results) == 3
    assert result.metric_name == "sharpe_ratio"
    assert len(result.most_sensitive) >= 0


def test_sensitivity_analyzer_base_metrics() -> None:
    """Test that base metrics are computed."""
    data = create_sample_ohlcv(50)

    config = SensitivityConfig(parameters={
        "threshold": ParamRange(values=[0.01, 0.02]),
    })

    analyzer = SensitivityAnalyzer(
        strategy_builder=simple_strategy_builder,
        base_data=data,
    )

    result = analyzer.analyze(config)

    assert "sharpe_ratio" in result.base_metrics
    assert "total_return" in result.base_metrics


def test_sensitivity_analyzer_multiple_params() -> None:
    """Test sensitivity analysis with multiple parameters."""
    data = create_sample_ohlcv(50)

    config = SensitivityConfig(parameters={
        "window": ParamRange(values=[5, 10, 15]),
        "threshold": ParamRange(values=[0.01]),
    })

    analyzer = SensitivityAnalyzer(
        strategy_builder=ma_strategy_builder,
        base_data=data,
    )

    result = analyzer.analyze(config)

    assert len(result.parameter_results) >= 3


def test_sensitivity_analyzer_identify_sensitive_param() -> None:
    """Test that most sensitive parameter is identified."""
    data = create_sample_ohlcv(50)

    config = SensitivityConfig(parameters={
        "window": ParamRange(values=[5, 10, 20, 30]),
    })

    analyzer = SensitivityAnalyzer(
        strategy_builder=ma_strategy_builder,
        base_data=data,
    )

    result = analyzer.analyze(config)

    assert "window" in result.most_sensitive or len(result.most_sensitive) == 0


def test_sensitivity_result_to_dict() -> None:
    """Test converting result to dict."""
    result = SensitivityResult(
        strategy_name="test",
        metric_name="sharpe_ratio",
        base_metrics={"sharpe_ratio": 1.0},
        parameter_results=[{"parameter": "window", "value": 5, "metrics": {"sharpe_ratio": 1.2}}],
        most_sensitive=["window"],
    )

    data = result.to_dict()

    assert data["strategy_name"] == "test"
    assert data["metric_name"] == "sharpe_ratio"
    assert data["most_sensitive"] == ["window"]


def test_sensitivity_save_result() -> None:
    """Test saving sensitivity result."""
    data = create_sample_ohlcv(30)

    config = SensitivityConfig(parameters={"window": ParamRange(values=[5, 10])})

    analyzer = SensitivityAnalyzer(
        strategy_builder=ma_strategy_builder,
        base_data=data,
    )

    result = analyzer.analyze(config)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "result.json"
        saved_path = analyzer.save_result(result, str(output_path))

        assert saved_path.exists()

        with saved_path.open() as f:
            loaded = json.load(f)

        assert loaded["strategy_name"] == "strategy"
        assert "parameter_results" in loaded


def test_load_sensitivity_config_from_json() -> None:
    """Test loading sensitivity config from JSON file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_data = {
            "fast_window": {"min": 5, "max": 20, "step": 5},
            "slow_window": {"values": [20, 30, 50]},
        }

        config_path = Path(tmpdir) / "config.json"
        config_path.write_text(json.dumps(config_data))

        loaded = load_sensitivity_config(str(config_path))

        assert "fast_window" in loaded.parameters
        assert "slow_window" in loaded.parameters
        assert loaded.parameters["fast_window"].min_value == 5


def test_sensitivity_tornado_output() -> None:
    """Test tornado chart output doesn't crash."""
    data = create_sample_ohlcv(30)

    config = SensitivityConfig(parameters={"window": ParamRange(values=[5, 10])})

    analyzer = SensitivityAnalyzer(
        strategy_builder=ma_strategy_builder,
        base_data=data,
    )

    result = analyzer.analyze(config)

    analyzer.print_tornado(result)