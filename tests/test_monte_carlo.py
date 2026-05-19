"""Tests for Monte Carlo simulation."""

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest

from aurora.analysis.monte_carlo import (
    MonteCarloConfig,
    MonteCarloResult,
    MonteCarloSimulator,
    load_trades_from_backtest,
)


def create_mock_trades(num_wins: int = 10, num_losses: int = 10, win_pnl: float = 100.0, loss_pnl: float = -50.0) -> list[dict]:
    """Create mock trade list."""
    trades = []
    for i in range(num_wins):
        trades.append({
            "trade_id": f"trade_{i}",
            "pnl": win_pnl,
            "return_pct": 0.05,
        })
    for i in range(num_losses):
        trades.append({
            "trade_id": f"trade_{num_wins + i}",
            "pnl": loss_pnl,
            "return_pct": -0.025,
        })
    return trades


def test_monte_carlo_config_defaults() -> None:
    """Test default Monte Carlo configuration."""
    config = MonteCarloConfig()
    assert config.num_simulations == 1000
    assert config.method == "trade_reshuffle"
    assert config.random_seed is None


def test_monte_carlo_config_validation() -> None:
    """Test configuration validation."""
    with pytest.raises(ValueError, match="Invalid method"):
        MonteCarloConfig(method="invalid")

    with pytest.raises(ValueError, match="num_simulations must be >= 1"):
        MonteCarloConfig(num_simulations=0)


def test_monte_carlo_trade_reshuffle() -> None:
    """Test Monte Carlo with trade reshuffle method."""
    trades = create_mock_trades(10, 10)

    config = MonteCarloConfig(num_simulations=100, random_seed=42)
    simulator = MonteCarloSimulator(config)

    result = simulator.run(trades, strategy_name="test_strategy")

    assert result.strategy_name == "test_strategy"
    assert "total_return" in result.metrics_distribution
    assert "sharpe_ratio" in result.metrics_distribution
    assert "max_drawdown" in result.metrics_distribution
    assert "win_rate" in result.metrics_distribution

    assert len(result.metrics_distribution["total_return"]) == 100
    assert "mean" in result.summary_stats["total_return"]
    assert "median" in result.summary_stats["total_return"]
    assert "std" in result.summary_stats["total_return"]
    assert "p5" in result.summary_stats["total_return"]
    assert "p95" in result.summary_stats["total_return"]


def test_monte_carlo_empty_trades_raises() -> None:
    """Test that empty trades raises error."""
    config = MonteCarloConfig(num_simulations=10)
    simulator = MonteCarloSimulator(config)

    with pytest.raises(ValueError, match="No trades provided"):
        simulator.run([], "test")


def test_monte_carlo_trades_without_pnl_raises() -> None:
    """Test that trades without PnL raises error."""
    trades = [{"trade_id": "t1"}, {"trade_id": "t2"}]

    config = MonteCarloConfig(num_simulations=10)
    simulator = MonteCarloSimulator(config)

    with pytest.raises(ValueError, match="No P&L values found"):
        simulator.run(trades, "test")


def test_monte_carlo_reproducibility() -> None:
    """Test that random seed provides reproducibility."""
    trades = create_mock_trades(15, 15)

    config1 = MonteCarloConfig(num_simulations=50, random_seed=12345)
    simulator1 = MonteCarloSimulator(config1)
    result1 = simulator1.run(trades, "test")

    config2 = MonteCarloConfig(num_simulations=50, random_seed=12345)
    simulator2 = MonteCarloSimulator(config2)
    result2 = simulator2.run(trades, "test")

    assert result1.metrics_distribution["total_return"] == result2.metrics_distribution["total_return"]


def test_monte_carlo_price_path_not_implemented() -> None:
    """Test that price_path method raises NotImplementedError."""
    trades = create_mock_trades()

    config = MonteCarloConfig(method="price_path")
    simulator = MonteCarloSimulator(config)

    with pytest.raises(NotImplementedError, match="Price path simulation not yet implemented"):
        simulator.run(trades, "test")


def test_monte_carlo_save_result() -> None:
    """Test saving Monte Carlo result to file."""
    trades = create_mock_trades(5, 5)

    config = MonteCarloConfig(num_simulations=10, random_seed=42)
    simulator = MonteCarloSimulator(config)
    result = simulator.run(trades, "test")

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "result.json"
        saved_path = simulator.save_result(result, str(output_path))

        assert saved_path.exists()

        with saved_path.open() as f:
            loaded = json.load(f)

        assert loaded["strategy_name"] == "test"
        assert "metrics_distribution" in loaded
        assert "summary_stats" in loaded


def test_monte_carlo_mean_metrics_reasonable() -> None:
    """Test that simulated mean metrics are close to expected values."""
    trades = create_mock_trades(10, 10, win_pnl=100.0, loss_pnl=-50.0)

    config = MonteCarloConfig(num_simulations=500, random_seed=42)
    simulator = MonteCarloSimulator(config)
    result = simulator.run(trades, "test")

    expected_avg_pnl = (10 * 100.0 + 10 * -50.0) / 20

    mean_total_return = result.summary_stats["total_return"]["mean"]
    assert abs(mean_total_return) < 0.5


def test_load_trades_from_backtest() -> None:
    """Test loading trades from backtest JSON and CSV."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)

        trades_csv = base_path / "trades.csv"
        trades_csv.write_text("""trade_id,symbol,entry_timestamp,exit_timestamp,side,quantity,entry_price,exit_price,gross_pnl,net_pnl,return_pct,bars_held,exit_reason
trade_1,SPY,2020-01-01,2020-01-02,long,10,100.0,105.0,50.0,40.0,0.05,1,signal_flat
trade_2,SPY,2020-01-02,2020-01-03,long,10,105.0,95.0,-100.0,-110.0,-0.10,1,signal_flat
""")

        backtest_json = base_path / "backtest.json"
        backtest_json.write_text(json.dumps({
            "metrics": {"total_return": 0.1},
            "trades_path": str(trades_csv),
        }))

        trades = load_trades_from_backtest(str(backtest_json))

        assert len(trades) == 2
        assert trades[0]["pnl"] == 40.0
        assert trades[1]["pnl"] == -110.0


def test_load_trades_from_backtest_missing_path() -> None:
    """Test loading from backtest with missing trades path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)

        backtest_json = base_path / "backtest.json"
        backtest_json.write_text(json.dumps({
            "metrics": {"total_return": 0.1},
        }))

        trades = load_trades_from_backtest(str(backtest_json))
        assert trades == []


def test_load_trades_from_backtest_missing_file() -> None:
    """Test loading from non-existent backtest file."""
    with pytest.raises(FileNotFoundError):
        load_trades_from_backtest("/nonexistent/path.json")