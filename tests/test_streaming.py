"""Tests for market data streaming."""

import sys
import time
from unittest.mock import patch

import pandas as pd
import pytest

from aurora.data.streaming import (
    AlpacaPaperStream,
    FakeMarketDataStream,
)
from aurora.data.streaming.base import Bar


def test_fake_stream_initialization() -> None:
    """Test FakeMarketDataStream initializes correctly."""
    dates = pd.date_range("2020-01-01", periods=10, freq="D")
    data = pd.DataFrame({
        "symbol": ["AAPL"] * 10,
        "timestamp": dates,
        "open": [100] * 10,
        "high": [102] * 10,
        "low": [98] * 10,
        "close": [101] * 10,
        "volume": [1000] * 10,
    })

    stream = FakeMarketDataStream(data, delay_seconds=0.01)
    assert stream is not None
    assert not stream.is_connected


def test_fake_stream_connect_disconnect() -> None:
    """Test connect and disconnect."""
    data = pd.DataFrame({
        "symbol": ["AAPL"],
        "timestamp": [pd.Timestamp("2020-01-01")],
        "open": [100],
        "high": [102],
        "low": [98],
        "close": [101],
        "volume": [1000],
    })

    stream = FakeMarketDataStream(data)
    stream.connect()
    assert stream.is_connected

    stream.disconnect()
    assert not stream.is_connected


def test_fake_stream_replay() -> None:
    """Test fake stream replays data correctly."""
    dates = pd.date_range("2020-01-01", periods=5, freq="D")
    data = pd.DataFrame({
        "symbol": ["AAPL"] * 5,
        "timestamp": dates,
        "open": [100, 101, 102, 103, 104],
        "high": [102, 103, 104, 105, 106],
        "low": [98, 99, 100, 101, 102],
        "close": [101, 102, 103, 104, 105],
        "volume": [1000, 1100, 1200, 1300, 1400],
    })

    stream = FakeMarketDataStream(data, delay_seconds=0.001)
    stream.connect()
    stream.subscribe(["AAPL"])

    bars_received = []

    def on_bar(bar: Bar):
        bars_received.append(bar)

    stream.on_bar(on_bar)
    stream.start_replay()

    time.sleep(0.1)
    stream.disconnect()

    assert len(bars_received) == 5
    assert bars_received[0].symbol == "AAPL"
    assert bars_received[0].close == 101.0


def test_fake_stream_callback() -> None:
    """Test callback invocation."""
    data = pd.DataFrame({
        "symbol": ["MSFT"],
        "timestamp": [pd.Timestamp("2020-01-01")],
        "open": [200],
        "high": [202],
        "low": [198],
        "close": [201],
        "volume": [500],
    })

    stream = FakeMarketDataStream(data, delay_seconds=0.001)
    stream.connect()
    stream.subscribe(["MSFT"])

    callback_invoked = False

    def on_bar(bar: Bar):
        nonlocal callback_invoked
        callback_invoked = True

    stream.on_bar(on_bar)
    stream.start_replay()

    time.sleep(0.05)
    stream.disconnect()

    assert callback_invoked


def test_fake_stream_filter_by_symbol() -> None:
    """Test that stream filters by subscribed symbols."""
    data = pd.DataFrame({
        "symbol": ["AAPL", "MSFT", "GOOG"],
        "timestamp": pd.date_range("2020-01-01", periods=3, freq="D"),
        "open": [100, 200, 300],
        "high": [102, 202, 302],
        "low": [98, 198, 298],
        "close": [101, 201, 301],
        "volume": [1000, 2000, 3000],
    })

    stream = FakeMarketDataStream(data, delay_seconds=0.001)
    stream.connect()
    stream.subscribe(["AAPL", "GOOG"])

    bars_received = []

    def on_bar(bar: Bar):
        bars_received.append(bar.symbol)

    stream.on_bar(on_bar)
    stream.start_replay()

    time.sleep(0.1)
    stream.disconnect()

    assert "AAPL" in bars_received
    assert "GOOG" in bars_received
    assert "MSFT" not in bars_received


def test_alpaca_stream_initialization() -> None:
    """Test AlpacaPaperStream initializes with env vars."""
    with patch.dict("os.environ", {
        "ALPACA_PAPER_API_KEY": "test_key",
        "ALPACA_PAPER_SECRET_KEY": "test_secret",
    }, clear=False):
        stream = AlpacaPaperStream()
        assert stream._api_key == "test_key"
        assert stream._secret_key == "test_secret"


def test_alpaca_stream_explicit_credentials() -> None:
    """Test AlpacaPaperStream accepts explicit credentials."""
    stream = AlpacaPaperStream(api_key="explicit_key", secret_key="explicit_secret")
    assert stream._api_key == "explicit_key"
    assert stream._secret_key == "explicit_secret"


def test_alpaca_stream_no_env_credentials() -> None:
    """Test AlpacaPaperStream with no env credentials."""
    with patch.dict("os.environ", {}, clear=True):
        stream = AlpacaPaperStream()
        assert stream._api_key is None
        assert stream._secret_key is None