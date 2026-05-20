"""Tests for commission models."""

import pytest

from aurora.brokers.commission import (
    FixedCommission,
    NoCommission,
    PerShareCommission,
)


def test_no_commission() -> None:
    """Test NoCommission returns zero."""
    model = NoCommission()
    assert model.calculate(10000.0, 100) == 0.0
    assert model.calculate(0.0, 0) == 0.0


def test_fixed_commission() -> None:
    """Test FixedCommission returns per-trade fee."""
    model = FixedCommission(per_trade=5.0)
    assert model.calculate(10000.0, 100) == 5.0
    assert model.calculate(100.0, 1) == 5.0


def test_fixed_commission_default() -> None:
    """Test FixedCommission default value."""
    model = FixedCommission()
    assert model.per_trade == 0.0
    assert model.calculate(10000.0, 100) == 0.0


def test_per_share_commission() -> None:
    """Test PerShareCommission returns per-share fee."""
    model = PerShareCommission(per_share=0.01)
    assert model.calculate(100.0, 100) == 1.0
    assert model.calculate(200.0, 50) == 0.5


def test_per_share_commission_default() -> None:
    """Test PerShareCommission default value."""
    model = PerShareCommission()
    assert model.per_share == 0.005
    assert model.calculate(100.0, 100) == 0.5


def test_per_share_commission_zero_shares() -> None:
    """Test PerShareCommission with zero shares."""
    model = PerShareCommission(per_share=0.01)
    assert model.calculate(0.0, 0) == 0.0


def test_commission_order_value_not_used_for_pershare() -> None:
    """Test PerShareCommission uses quantity, not order_value."""
    model = PerShareCommission(per_share=0.01)
    assert model.calculate(10000.0, 100) == 1.0
    assert model.calculate(100.0, 100) == 1.0