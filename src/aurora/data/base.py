"""Base interfaces for market data adapters."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd


@dataclass(frozen=True)
class DataSourceHealth:
    """Health status for a market data source."""

    source_name: str
    ok: bool
    message: str
    checked_at: str


@dataclass(frozen=True)
class MarketDataRequest:
    """Request parameters for OHLCV market data."""

    symbols: list[str]
    start: str
    end: str | None = None
    interval: str = "1d"
    adjusted: bool = True


class MarketDataSource(ABC):
    """Abstract base class for market data sources."""

    source_name: str

    @abstractmethod
    def get_bars(self, request: MarketDataRequest) -> pd.DataFrame:
        """Return standard OHLCV bars for the request."""

    @abstractmethod
    def health_check(self) -> DataSourceHealth:
        """Return data source health information."""


def utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()
