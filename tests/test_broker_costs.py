"""Tests for broker slippage and commission integration."""

import pytest

from aurora.brokers.alpaca_adapter import FakeAlpacaPaperClient
from aurora.brokers.commission import FixedCommission, NoCommission, PerShareCommission
from aurora.brokers.slippage import FixedSlippage, NoSlippage, PercentageSlippage


def test_fake_client_default_no_slippage_no_commission() -> None:
    """Test FakeAlpacaPaperClient with default models."""
    client = FakeAlpacaPaperClient()
    result = client.submit_paper_order("AAPL", 100, "buy")

    assert result["slippage_applied"] == 0.0
    assert result["commission_charged"] == 0.0
    assert result["fill_price"] == 100.0


def test_fake_client_with_fixed_slippage() -> None:
    """Test FakeAlpacaPaperClient with FixedSlippage."""
    client = FakeAlpacaPaperClient(slippage_model=FixedSlippage(cents=0.10))
    result = client.submit_paper_order("AAPL", 100, "buy")

    assert result["fill_price"] == pytest.approx(100.10)
    assert result["slippage_applied"] == pytest.approx(0.10)


def test_fake_client_with_percentage_slippage() -> None:
    """Test FakeAlpacaPaperClient with PercentageSlippage."""
    client = FakeAlpacaPaperClient(slippage_model=PercentageSlippage(percent=0.01))
    result = client.submit_paper_order("AAPL", 100, "buy", price=100.0)

    assert result["fill_price"] == 101.0
    assert result["slippage_applied"] == 1.0


def test_fake_client_with_fixed_commission() -> None:
    """Test FakeAlpacaPaperClient with FixedCommission."""
    client = FakeAlpacaPaperClient(commission_model=FixedCommission(per_trade=5.0))
    result = client.submit_paper_order("AAPL", 100, "buy")

    assert result["commission_charged"] == 5.0


def test_fake_client_with_per_share_commission() -> None:
    """Test FakeAlpacaPaperClient with PerShareCommission."""
    client = FakeAlpacaPaperClient(commission_model=PerShareCommission(per_share=0.01))
    result = client.submit_paper_order("AAPL", 100, "buy")

    assert result["commission_charged"] == 1.0


def test_fake_client_slippage_sell_side() -> None:
    """Test slippage applied correctly on sell side."""
    client = FakeAlpacaPaperClient(slippage_model=FixedSlippage(cents=0.05))
    result = client.submit_paper_order("AAPL", 100, "sell")

    assert result["fill_price"] == pytest.approx(99.95)
    assert result["slippage_applied"] == pytest.approx(-0.05)


def test_fake_client_custom_price() -> None:
    """Test FakeAlpacaPaperClient uses custom price."""
    client = FakeAlpacaPaperClient()
    result = client.submit_paper_order("AAPL", 100, "buy", price=150.0)

    assert result["fill_price"] == 150.0


def test_fake_client_both_models() -> None:
    """Test FakeAlpacaPaperClient with both slippage and commission."""
    client = FakeAlpacaPaperClient(
        slippage_model=FixedSlippage(cents=0.05),
        commission_model=FixedCommission(per_trade=2.0),
    )
    result = client.submit_paper_order("AAPL", 100, "buy", price=100.0)

    assert result["fill_price"] == pytest.approx(100.05)
    assert result["slippage_applied"] == pytest.approx(0.05)
    assert result["commission_charged"] == 2.0