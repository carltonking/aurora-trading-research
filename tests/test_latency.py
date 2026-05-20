"""Tests for latency models."""

import pytest

from aurora.brokers.latency import FixedLatency, NoLatency, RandomLatency


def test_no_latency() -> None:
    """Test NoLatency returns zero."""
    model = NoLatency()
    assert model.delay({"symbol": "AAPL", "qty": 100}) == 0.0


def test_fixed_latency() -> None:
    """Test FixedLatency returns fixed seconds."""
    model = FixedLatency(seconds=2.5)
    assert model.delay({"symbol": "AAPL", "qty": 100}) == 2.5


def test_fixed_latency_default() -> None:
    """Test FixedLatency default value."""
    model = FixedLatency()
    assert model.seconds == 1.0
    assert model.delay({}) == 1.0


def test_random_latency() -> None:
    """Test RandomLatency returns value in range."""
    model = RandomLatency(min_seconds=0.5, max_seconds=2.0)
    results = [model.delay({"symbol": "AAPL"}) for _ in range(100)]
    assert all(0.5 <= r <= 2.0 for r in results)


def test_random_latency_default() -> None:
    """Test RandomLatency default values."""
    model = RandomLatency()
    assert model.min_seconds == 0.5
    assert model.max_seconds == 2.0


def test_random_latency_deterministic() -> None:
    """Test RandomLatency returns different values (not deterministic)."""
    model = RandomLatency(min_seconds=0.0, max_seconds=1.0)
    results = set(model.delay({}) for _ in range(10))
    assert len(results) > 1