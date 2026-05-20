"""Fake market data stream for testing and replay."""

import time
import threading
from typing import Optional

import pandas as pd

from aurora.data.streaming.base import Bar, MarketDataStream


class FakeMarketDataStream(MarketDataStream):
    """Replays historical OHLCV data with a configurable delay."""

    def __init__(self, data: pd.DataFrame, delay_seconds: float = 1.0) -> None:
        """Initialize fake stream with historical data.

        Args:
            data: DataFrame with columns: symbol, timestamp, open, high, low, close, volume
            delay_seconds: Delay between each bar (default 1 second)
        """
        super().__init__()
        self._data = data
        self._delay_seconds = delay_seconds
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._symbols: list[str] = []

    def connect(self) -> None:
        """Connect to the fake stream (no-op)."""
        self._connected = True

    def disconnect(self) -> None:
        """Disconnect and stop replay."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._connected = False

    def subscribe(self, symbols: list[str]) -> None:
        """Subscribe to symbols for replay."""
        self._symbols = symbols
        self._filtered_data = self._data[self._data["symbol"].isin(symbols)]

    def start_replay(self) -> None:
        """Start replaying data in a background thread."""
        if not self._connected:
            raise RuntimeError("Must connect before replay")
        if not self._symbols:
            raise RuntimeError("Must subscribe to symbols before replay")

        self._running = True
        self._thread = threading.Thread(target=self._replay_worker, daemon=True)
        self._thread.start()

    def _replay_worker(self) -> None:
        """Worker that replays bars with delay."""
        for _, row in self._filtered_data.iterrows():
            if not self._running:
                break
            bar = Bar(
                symbol=row["symbol"],
                timestamp=str(row["timestamp"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=int(row["volume"]),
            )
            if self._bar_callback is not None:
                self._bar_callback(bar)
            time.sleep(self._delay_seconds)

    @property
    def latest_bar(self) -> Optional[Bar]:
        """Get the most recent bar (only valid after replay)."""
        return getattr(self, "_last_bar", None)