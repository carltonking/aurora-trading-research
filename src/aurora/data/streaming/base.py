"""Streaming market data base classes and interfaces."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class Bar:
    """Represents a single bar of OHLCV data."""

    symbol: str
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass
class Quote:
    """Represents a quote (bid/ask)."""

    symbol: str
    timestamp: str
    bid: float
    ask: float
    bid_size: int
    ask_size: int


class MarketDataStream(ABC):
    """Abstract base class for market data streaming."""

    @abstractmethod
    def connect(self) -> None:
        """Connect to the data stream."""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from the data stream."""
        pass

    @abstractmethod
    def subscribe(self, symbols: list[str]) -> None:
        """Subscribe to symbols."""
        pass

    def on_bar(self, callback: Callable[[Bar], None]) -> None:
        """Set callback for bar updates."""
        self._bar_callback = callback

    def on_quote(self, callback: Callable[[Quote], None]) -> None:
        """Set callback for quote updates."""
        self._quote_callback = callback

    @property
    def is_connected(self) -> bool:
        """Return True if connected."""
        return self._connected

    def __init__(self) -> None:
        self._connected = False
        self._bar_callback: Optional[Callable[[Bar], None]] = None
        self._quote_callback: Optional[Callable[[Quote], None]] = None