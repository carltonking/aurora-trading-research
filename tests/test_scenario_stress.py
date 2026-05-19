"""Tests for scenario stress testing."""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from aurora.analysis.scenario_stress import (
    BUILT_IN_SCENARIOS,
    Scenario,
    ScenarioEvent,
    StressTestResult,
    StressTester,
    load_scenario,
    list_built_in_scenarios,
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


def simple_long_strategy(data: pd.DataFrame) -> pd.Series:
    """Simple always-long strategy."""
    return pd.Series(1, index=data.index, dtype=int)


def moving_average_strategy(data: pd.DataFrame) -> pd.Series:
    """Simple moving average strategy."""
    signals = pd.Series(0, index=data.index, dtype=int)
    if "close" in data.columns:
        ma = data["close"].rolling(window=5).mean()
        signals[data["close"] > ma] = 1
    return signals


def test_scenario_from_dict() -> None:
    """Test creating scenario from dict."""
    data = {
        "name": "Test Scenario",
        "description": "Test scenario description",
        "events": [
            {
                "start_date": "2020-01-01",
                "end_date": "2020-03-31",
                "price_multiplier": 0.8,
                "volatility_multiplier": 2.0,
            }
        ],
    }

    scenario = Scenario.from_dict(data)
    assert scenario.name == "Test Scenario"
    assert len(scenario.events) == 1
    assert scenario.events[0].price_multiplier == 0.8


def test_scenario_to_dict() -> None:
    """Test converting scenario to dict."""
    scenario = Scenario(
        name="Test",
        description="Test desc",
        events=[
            ScenarioEvent("2020-01-01", "2020-03-31", 0.9, 1.5)
        ],
    )

    data = scenario.to_dict()
    assert data["name"] == "Test"
    assert len(data["events"]) == 1


def test_stress_tester_basic() -> None:
    """Test basic stress test."""
    data = create_sample_ohlcv(50)
    tester = StressTester(strategy_fn=simple_long_strategy)

    scenario = Scenario(
        name="Test Crash",
        description="Test scenario",
        events=[ScenarioEvent("2020-01-15", "2020-02-15", 0.8, 2.0)],
    )

    result = tester.run_scenario(data, scenario, "test_strategy")

    assert result.strategy_name == "test_strategy"
    assert result.scenario_name == "Test Crash"
    assert "total_return" in result.original_metrics
    assert "total_return" in result.stressed_metrics


def test_stress_tester_metrics_change() -> None:
    """Test that stressed metrics differ from original."""
    data = create_sample_ohlcv(100)
    tester = StressTester(strategy_fn=moving_average_strategy)

    scenario = Scenario(
        name="Crash",
        description="Test",
        events=[ScenarioEvent("2020-02-01", "2020-03-31", 0.6, 3.0)],
    )

    result = tester.run_scenario(data, scenario, "test")

    assert result.stressed_metrics["max_drawdown"] >= result.original_metrics["max_drawdown"]


def test_built_in_scenarios() -> None:
    """Test built-in scenarios exist."""
    assert len(BUILT_IN_SCENARIOS) == 4
    assert "2008_financial_crisis" in BUILT_IN_SCENARIOS
    assert "2020_covid_crash" in BUILT_IN_SCENARIOS
    assert "interest_rate_spike" in BUILT_IN_SCENARIOS
    assert "bull_market_meltdown" in BUILT_IN_SCENARIOS


def test_list_built_in_scenarios() -> None:
    """Test listing built-in scenarios."""
    scenarios = list_built_in_scenarios()
    assert len(scenarios) == 4
    assert "2008_financial_crisis" in scenarios


def test_stress_tester_all_scenarios() -> None:
    """Test running all scenarios."""
    data = create_sample_ohlcv(50)
    tester = StressTester(strategy_fn=simple_long_strategy)

    results = tester.run_all_scenarios(data)

    assert len(results) == 4
    for result in results:
        assert result.strategy_name == "strategy"
        assert result.scenario_name


def test_stress_tester_save_result() -> None:
    """Test saving stress test result."""
    data = create_sample_ohlcv(30)
    tester = StressTester(strategy_fn=simple_long_strategy)

    scenario = Scenario("Test", "Test", [ScenarioEvent("2020-01-15", "2020-02-15", 0.8, 2.0)])
    result = tester.run_scenario(data, scenario, "test")

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "result.json"
        saved_path = tester.save_result(result, str(output_path))

        assert saved_path.exists()

        with saved_path.open() as f:
            loaded = json.load(f)

        assert loaded["strategy_name"] == "test"
        assert "original_metrics" in loaded
        assert "stressed_metrics" in loaded


def test_load_scenario_from_json() -> None:
    """Test loading scenario from JSON file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        scenario_data = {
            "name": "Custom Scenario",
            "description": "Custom stress test",
            "events": [
                {
                    "start_date": "2020-01-01",
                    "end_date": "2020-06-30",
                    "price_multiplier": 0.7,
                    "volatility_multiplier": 2.5,
                }
            ],
        }

        scenario_path = Path(tmpdir) / "scenario.json"
        scenario_path.write_text(json.dumps(scenario_data))

        loaded = load_scenario(str(scenario_path))
        assert loaded.name == "Custom Scenario"
        assert len(loaded.events) == 1
        assert loaded.events[0].price_multiplier == 0.7


def test_stress_tester_empty_data() -> None:
    """Test stress test with minimal data."""
    data = create_sample_ohlcv(10)
    tester = StressTester(strategy_fn=simple_long_strategy)

    scenario = Scenario("Test", "Test", [ScenarioEvent("2020-01-01", "2020-01-10", 0.5, 3.0)])
    result = tester.run_scenario(data, scenario, "test")

    assert result.original_metrics["trade_count"] >= 0
    assert result.stressed_metrics["trade_count"] >= 0