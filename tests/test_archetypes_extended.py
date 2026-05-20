"""Tests for new strategy archetypes."""

import pandas as pd
import pytest

from aurora.strategies.archetypes import (
    GridTradingStrategy,
    PairsTradingStrategy,
    DollarCostAveragingStrategy,
)


def create_sample_data(symbol: str = "AAPL", periods: int = 100, start_price: float = 100.0) -> pd.DataFrame:
    """Create sample OHLCV data for testing."""
    dates = pd.date_range(start="2020-01-01", periods=periods, freq="D")
    data = {
        "open": start_price + pd.Series(range(periods)) * 0.5,
        "high": start_price + pd.Series(range(periods)) * 0.5 + 2,
        "low": start_price + pd.Series(range(periods)) * 0.5 - 2,
        "close": start_price + pd.Series(range(periods)) * 0.5,
        "volume": 1000000,
    }
    return pd.DataFrame(data, index=dates)


class TestGridTradingStrategy:
    """Tests for GridTradingStrategy."""

    def test_initialization(self) -> None:
        """Test strategy initializes with default values."""
        strategy = GridTradingStrategy()
        assert strategy.grid_spacing_pct == 0.02
        assert strategy.grid_levels == 5
        assert strategy.strategy_name == "grid_trading"

    def test_custom_parameters(self) -> None:
        """Test strategy with custom parameters."""
        strategy = GridTradingStrategy(grid_spacing_pct=0.05, grid_levels=10)
        assert strategy.grid_spacing_pct == 0.05
        assert strategy.grid_levels == 10

    def test_invalid_parameters(self) -> None:
        """Test strategy rejects invalid parameters."""
        with pytest.raises(ValueError):
            GridTradingStrategy(grid_spacing_pct=0.0)
        with pytest.raises(ValueError):
            GridTradingStrategy(grid_levels=0)

    def test_generate_signal(self) -> None:
        """Test signal generation."""
        data = create_sample_data()
        strategy = GridTradingStrategy()
        signals = strategy.generate_signal(data)

        assert isinstance(signals, pd.Series)
        assert len(signals) == len(data)
        assert set(signals.unique()).issubset({0, 1})

    def test_repr(self) -> None:
        """Test __repr__ shows parameters."""
        strategy = GridTradingStrategy(grid_spacing_pct=0.05, grid_levels=10)
        repr_str = repr(strategy)
        assert "0.05" in repr_str
        assert "10" in repr_str


class TestPairsTradingStrategy:
    """Tests for PairsTradingStrategy."""

    def test_initialization(self) -> None:
        """Test strategy initializes with default values."""
        strategy = PairsTradingStrategy()
        assert strategy.symbol_a == "SPY"
        assert strategy.symbol_b == "SH"
        assert strategy.lookback == 60
        assert strategy.strategy_name == "pairs_trading"

    def test_custom_parameters(self) -> None:
        """Test strategy with custom parameters."""
        strategy = PairsTradingStrategy(symbol_a="AAPL", symbol_b="MSFT", lookback=30)
        assert strategy.symbol_a == "AAPL"
        assert strategy.symbol_b == "MSFT"
        assert strategy.lookback == 30

    def test_invalid_parameters(self) -> None:
        """Test strategy rejects invalid parameters."""
        with pytest.raises(ValueError):
            PairsTradingStrategy(lookback=1)
        with pytest.raises(ValueError):
            PairsTradingStrategy(entry_z=0.5, exit_z=1.0)

    def test_generate_signal_with_multi_column(self) -> None:
        """Test signal generation with multi-column data."""
        dates = pd.date_range(start="2020-01-01", periods=100, freq="D")
        data = pd.DataFrame({
            "spy_close": 100 + pd.Series(range(100)) * 0.5,
            "sh_close": 50 + pd.Series(range(100)) * 0.2,
        }, index=dates)

        strategy = PairsTradingStrategy(symbol_a="SPY", symbol_b="SH", lookback=20, entry_z=1.5)
        signals = strategy.generate_signal(data)

        assert isinstance(signals, pd.Series)
        assert len(signals) == len(data)
        assert set(signals.unique()).issubset({-1, 0, 1})

    def test_repr(self) -> None:
        """Test __repr__ shows parameters."""
        strategy = PairsTradingStrategy(symbol_a="AAPL", symbol_b="MSFT", lookback=30)
        repr_str = repr(strategy)
        assert "AAPL" in repr_str
        assert "MSFT" in repr_str


class TestDollarCostAveragingStrategy:
    """Tests for DollarCostAveragingStrategy."""

    def test_initialization(self) -> None:
        """Test strategy initializes with default values."""
        strategy = DollarCostAveragingStrategy()
        assert strategy.interval == "monthly"
        assert strategy.amount == 1000.0
        assert strategy.strategy_name == "dca"

    def test_custom_parameters(self) -> None:
        """Test strategy with custom parameters."""
        strategy = DollarCostAveragingStrategy(interval="weekly", amount=500.0)
        assert strategy.interval == "weekly"
        assert strategy.amount == 500.0

    def test_invalid_interval(self) -> None:
        """Test strategy rejects invalid interval."""
        with pytest.raises(ValueError):
            DollarCostAveragingStrategy(interval="yearly")

    def test_generate_signal_monthly(self) -> None:
        """Test monthly signal generation."""
        dates = pd.date_range(start="2020-01-01", periods=365, freq="D")
        data = pd.DataFrame({"close": 100 + pd.Series(range(365)) * 0.1}, index=dates)

        strategy = DollarCostAveragingStrategy(interval="monthly")
        signals = strategy.generate_signal(data)

        assert isinstance(signals, pd.Series)
        assert len(signals) == len(data)
        assert signals.sum() > 0

    def test_generate_signal_weekly(self) -> None:
        """Test weekly signal generation."""
        dates = pd.date_range(start="2020-01-01", periods=90, freq="D")
        data = pd.DataFrame({"close": 100 + pd.Series(range(90)) * 0.1}, index=dates)

        strategy = DollarCostAveragingStrategy(interval="weekly")
        signals = strategy.generate_signal(data)

        assert isinstance(signals, pd.Series)
        assert signals.sum() > 12

    def test_generate_signal_daily(self) -> None:
        """Test daily signal generation."""
        dates = pd.date_range(start="2020-01-01", periods=30, freq="D")
        data = pd.DataFrame({"close": 100 + pd.Series(range(30)) * 0.1}, index=dates)

        strategy = DollarCostAveragingStrategy(interval="daily")
        signals = strategy.generate_signal(data)

        assert isinstance(signals, pd.Series)
        assert signals.sum() > 25

    def test_repr(self) -> None:
        """Test __repr__ shows parameters."""
        strategy = DollarCostAveragingStrategy(interval="weekly", amount=500.0)
        repr_str = repr(strategy)
        assert "weekly" in repr_str
        assert "500" in repr_str


def test_archetypes_registry() -> None:
    """Test that archetypes are properly registered."""
    from aurora.strategies.archetypes import get_archetype

    assert get_archetype("grid_trading") == GridTradingStrategy
    assert get_archetype("pairs_trading") == PairsTradingStrategy
    assert get_archetype("dca") == DollarCostAveragingStrategy

    with pytest.raises(ValueError, match="Unknown archetype"):
        get_archetype("unknown")