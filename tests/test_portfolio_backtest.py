"""Tests for portfolio backtest."""

import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from aurora.backtesting.portfolio_backtest import (
    PortfolioBacktestResult,
    run_portfolio_backtest,
    save_portfolio_result,
)
from aurora.data.universe import Universe


def create_sample_ohlcv(days: int = 50, start_price: float = 100.0) -> pd.DataFrame:
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


def ma_crossover_strategy(data: pd.DataFrame) -> pd.DataFrame:
    """Simple moving average crossover strategy."""
    result = data.copy()
    ma_fast = result["close"].rolling(window=5).mean()
    ma_slow = result["close"].rolling(window=20).mean()
    result["signal"] = 0
    result.loc[result["close"] > ma_slow, "signal"] = 1
    return result


def always_long_strategy(data: pd.DataFrame) -> pd.DataFrame:
    """Always long strategy."""
    result = data.copy()
    result["signal"] = 1
    return result


def test_portfolio_backtest_single_symbol() -> None:
    """Test portfolio backtest with single symbol."""
    universe = Universe(name="test", symbols=["AAPL"])

    data = {"AAPL": create_sample_ohlcv(50)}

    result = run_portfolio_backtest(
        strategy_fn=ma_crossover_strategy,
        universe=universe,
        start_date="2020-01-01",
        end_date="2020-03-01",
        initial_capital=100000,
        data_fetcher=lambda *args, **kwargs: data,
    )

    assert result.universe_name == "test"
    assert "total_return" in result.metrics
    assert "sharpe_ratio" in result.metrics


def test_portfolio_backtest_multiple_symbols() -> None:
    """Test portfolio backtest with multiple symbols."""
    universe = Universe(name="test", symbols=["AAPL", "MSFT", "GOOGL"])

    data = {
        "AAPL": create_sample_ohlcv(50),
        "MSFT": create_sample_ohlcv(50),
        "GOOGL": create_sample_ohlcv(50),
    }

    result = run_portfolio_backtest(
        strategy_fn=ma_crossover_strategy,
        universe=universe,
        start_date="2020-01-01",
        end_date="2020-03-01",
        initial_capital=100000,
        data_fetcher=lambda *args, **kwargs: data,
    )

    assert result.total_trades >= 0
    assert "AAPL" in result.per_symbol_metrics
    assert "MSFT" in result.per_symbol_metrics
    assert "GOOGL" in result.per_symbol_metrics


def test_portfolio_backtest_custom_weights() -> None:
    """Test portfolio backtest with custom weights."""
    universe = Universe(name="test", symbols=["AAPL", "MSFT"])

    data = {
        "AAPL": create_sample_ohlcv(50),
        "MSFT": create_sample_ohlcv(50),
    }

    weights = {"AAPL": 0.7, "MSFT": 0.3}

    result = run_portfolio_backtest(
        strategy_fn=ma_crossover_strategy,
        universe=universe,
        start_date="2020-01-01",
        end_date="2020-03-01",
        initial_capital=100000,
        weights=weights,
        data_fetcher=lambda *args, **kwargs: data,
    )

    assert result.total_trades >= 0


def test_portfolio_correlation_matrix() -> None:
    """Test that correlation matrix is computed."""
    universe = Universe(name="test", symbols=["AAPL", "MSFT"])

    data = {
        "AAPL": create_sample_ohlcv(50),
        "MSFT": create_sample_ohlcv(50),
    }

    result = run_portfolio_backtest(
        strategy_fn=always_long_strategy,
        universe=universe,
        start_date="2020-01-01",
        end_date="2020-03-01",
        initial_capital=100000,
        data_fetcher=lambda *args, **kwargs: data,
    )

    assert "AAPL" in result.correlation_matrix
    assert "AAPL" in result.correlation_matrix.get("MSFT", {})


def test_portfolio_backtest_empty_data() -> None:
    """Test portfolio with empty data returns zero metrics."""
    universe = Universe(name="test", symbols=["AAPL"])

    data = {"AAPL": pd.DataFrame()}

    result = run_portfolio_backtest(
        strategy_fn=ma_crossover_strategy,
        universe=universe,
        start_date="2020-01-01",
        end_date="2020-03-01",
        initial_capital=100000,
        data_fetcher=lambda *args, **kwargs: data,
    )

    assert result.metrics["total_return"] == 0.0


def test_portfolio_backtest_missing_symbol_graceful() -> None:
    """Test that missing symbol in data is handled gracefully."""
    universe = Universe(name="test", symbols=["AAPL", "MSFT", "GOOGL"])

    data = {
        "AAPL": create_sample_ohlcv(50),
        "MSFT": create_sample_ohlcv(50),
    }

    result = run_portfolio_backtest(
        strategy_fn=ma_crossover_strategy,
        universe=universe,
        start_date="2020-01-01",
        end_date="2020-03-01",
        initial_capital=100000,
        data_fetcher=lambda *args, **kwargs: data,
    )

    assert "AAPL" in result.per_symbol_metrics
    assert "MSFT" in result.per_symbol_metrics
    assert "GOOGL" not in result.per_symbol_metrics


def test_save_portfolio_result() -> None:
    """Test saving portfolio result to JSON."""
    universe = Universe(name="test", symbols=["AAPL"])

    data = {"AAPL": create_sample_ohlcv(30)}

    result = run_portfolio_backtest(
        strategy_fn=always_long_strategy,
        universe=universe,
        start_date="2020-01-01",
        end_date="2020-02-01",
        initial_capital=100000,
        data_fetcher=lambda *args, **kwargs: data,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "result.json"
        saved_path = save_portfolio_result(result, str(output_path))

        assert saved_path.exists()

        with saved_path.open() as f:
            loaded = json.load(f)

        assert loaded["universe_name"] == "test"
        assert "metrics" in loaded


def test_portfolio_backtest_to_dict() -> None:
    """Test converting result to dict."""
    result = PortfolioBacktestResult(
        universe_name="test",
        total_trades=10,
        metrics={"total_return": 0.1},
        per_symbol_metrics={"AAPL": {"total_return": 0.05}},
        correlation_matrix={"AAPL": {"AAPL": 1.0}},
        trades=[{"symbol": "AAPL", "pnl": 100}],
    )

    data = result.to_dict()

    assert data["universe_name"] == "test"
    assert data["total_trades"] == 10
    assert len(data["trades"]) == 1