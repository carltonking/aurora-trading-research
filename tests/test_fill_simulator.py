"""Tests for fill simulation models."""

import pytest

from aurora.brokers.fill_simulator import (
    ImmediateFill,
    PartialFill,
    QueueDelayFill,
)
from aurora.brokers.latency import FixedLatency


def test_immediate_fill() -> None:
    """Test ImmediateFill returns full quantity."""
    model = ImmediateFill()
    order = {"symbol": "AAPL", "qty": 100, "price": 150.0}
    result = model.simulate_fill(order)

    assert result["filled_qty"] == 100
    assert result["average_price"] == 150.0
    assert result["status"] == "filled"


def test_immediate_fill_zero_qty() -> None:
    """Test ImmediateFill with zero quantity."""
    model = ImmediateFill()
    order = {"symbol": "AAPL", "qty": 0, "price": 150.0}
    result = model.simulate_fill(order)

    assert result["filled_qty"] == 0
    assert result["status"] == "filled"


def test_partial_fill_full() -> None:
    """Test PartialFill with high probability can return full or near-full fill."""
    model = PartialFill(fill_probability=1.0, partial_pct_mean=0.95)
    order = {"symbol": "AAPL", "qty": 100, "price": 150.0}

    results = [model.simulate_fill(order) for _ in range(20)]
    full_fills = [r for r in results if r["filled_qty"] >= 90]

    assert len(full_fills) > 0


def test_partial_fill_probability() -> None:
    """Test PartialFill respects probability."""
    model = PartialFill(fill_probability=0.0, partial_pct_mean=0.5)
    order = {"symbol": "AAPL", "qty": 100, "price": 150.0}
    results = [model.simulate_fill(order) for _ in range(100)]

    no_fills = sum(1 for r in results if r["status"] == "no_fill")
    assert no_fills >= 95


def test_partial_fill_partial() -> None:
    """Test PartialFill can return partial fill."""
    model = PartialFill(fill_probability=1.0, partial_pct_mean=0.5)
    order = {"symbol": "AAPL", "qty": 100, "price": 150.0}

    results = [model.simulate_fill(order) for _ in range(100)]
    partials = [r for r in results if r["status"] == "partial"]

    assert len(partials) > 0
    assert all(0 < r["filled_qty"] < 100 for r in partials)


def test_queue_delay_fill_includes_latency() -> None:
    """Test QueueDelayFill includes latency in result."""
    base = ImmediateFill()
    latency = FixedLatency(seconds=1.5)
    model = QueueDelayFill(base, latency)

    order = {"symbol": "AAPL", "qty": 100, "price": 150.0}
    result = model.simulate_fill(order)

    assert "latency_seconds" in result
    assert result["latency_seconds"] == 1.5


def test_queue_delay_fill_preserves_fill() -> None:
    """Test QueueDelayFill preserves fill result."""
    base = ImmediateFill()
    latency = FixedLatency(seconds=0.0)
    model = QueueDelayFill(base, latency)

    order = {"symbol": "AAPL", "qty": 100, "price": 150.0}
    result = model.simulate_fill(order)

    assert result["filled_qty"] == 100
    assert result["status"] == "filled"