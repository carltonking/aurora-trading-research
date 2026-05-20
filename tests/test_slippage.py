"""Tests for slippage models."""

import pytest

from aurora.brokers.slippage import (
    FixedSlippage,
    NoSlippage,
    PercentageSlippage,
)


def test_no_slippage() -> None:
    """Test NoSlippage returns original price."""
    model = NoSlippage()
    assert model.apply(100.0, "buy", 100) == 100.0
    assert model.apply(100.0, "sell", 100) == 100.0


def test_fixed_slippage_buy() -> None:
    """Test FixedSlippage adds cents for buy orders."""
    model = FixedSlippage(cents=0.05)
    result = model.apply(100.0, "buy", 100)
    assert result == 100.05


def test_fixed_slippage_sell() -> None:
    """Test FixedSlippage subtracts cents for sell orders."""
    model = FixedSlippage(cents=0.05)
    result = model.apply(100.0, "sell", 100)
    assert result == 99.95


def test_fixed_slippage_case_insensitive() -> None:
    """Test FixedSlippage handles case insensitive sides."""
    model = FixedSlippage(cents=0.05)
    assert model.apply(100.0, "BUY", 100) == 100.05
    assert model.apply(100.0, "SELL", 100) == 99.95


def test_percentage_slippage_buy() -> None:
    """Test PercentageSlippage adds percentage for buy orders."""
    model = PercentageSlippage(percent=0.01)
    result = model.apply(100.0, "buy", 100)
    assert result == 101.0


def test_percentage_slippage_sell() -> None:
    """Test PercentageSlippage subtracts percentage for sell orders."""
    model = PercentageSlippage(percent=0.01)
    result = model.apply(100.0, "sell", 100)
    assert result == 99.0


def test_percentage_slippage_custom() -> None:
    """Test PercentageSlippage with custom percentage."""
    model = PercentageSlippage(percent=0.005)
    result = model.apply(200.0, "buy", 50)
    assert result == 201.0


def test_default_values() -> None:
    """Test default values."""
    fixed = FixedSlippage()
    assert fixed.cents == 0.01

    pct = PercentageSlippage()
    assert pct.percent == 0.001