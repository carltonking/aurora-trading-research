"""FRED macroeconomic data source.

Optional data source for Federal Reserve Economic Data.
Uses fredapi package (optional dependency).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

import pandas as pd

logger = logging.getLogger(__name__)

try:
    from fredapi import Fred
    FREDAPI_AVAILABLE = True
except ImportError:
    FREDAPI_AVAILABLE = False
    logger.warning("fredapi not available. FRED source disabled.")


@dataclass
class FredConfig:
    """Configuration for FRED data source."""

    api_key: Optional[str] = None
    enabled: bool = False

    def __post_init__(self) -> None:
        """Load config from environment if not provided."""
        if self.api_key is None:
            self.api_key = os.getenv("FRED_API_KEY")
        if not self.enabled:
            self.enabled = os.getenv("FRED_ENABLED", "false").lower() == "true"

    def __repr__(self) -> str:
        """Mask API key in repr."""
        key_mask = "****" if self.api_key else "None"
        return f"FredConfig(enabled={self.enabled}, api_key={key_mask})"


class FredSource:
    """FRED data source for macroeconomic indicators."""

    def __init__(self, config: Optional[FredConfig] = None) -> None:
        """Initialize FRED source.

        Args:
            config: FRED configuration. If None, loads from env.
        """
        self._config = config or FredConfig()
        self._client: Optional[Fred] = None

        if self._config.enabled and self._config.api_key:
            if not FREDAPI_AVAILABLE:
                raise ImportError(
                    "fredapi package required for FRED source. "
                    "Install with: pip install fredapi"
                )
            self._client = Fred(api_key=self._config.api_key)

    @property
    def enabled(self) -> bool:
        """Check if source is enabled."""
        return self._config.enabled

    def fetch_series(
        self,
        series_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """Fetch a FRED series.

        Args:
            series_id: FRED series identifier (e.g., "GDP", "UNRATE").
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            DataFrame with date and value columns.

        Raises:
            ValueError: If source is disabled.
            ImportError: If fredapi not installed.
        """
        if not self._config.enabled:
            raise ValueError("FRED source is not enabled. Set FRED_ENABLED=true.")

        if not self._client:
            if not FREDAPI_AVAILABLE:
                raise ImportError("fredapi package not installed.")
            raise ValueError("FRED API key not configured. Set FRED_API_KEY environment variable.")

        try:
            data = self._client.get_series(
                series_id,
                observation_start=start_date,
                observation_end=end_date,
            )

            if data is None or data.empty:
                return pd.DataFrame(columns=["date", "value"])

            df = pd.DataFrame({"date": data.index, "value": data.values})
            return df

        except Exception as e:
            logger.error(f"Error fetching FRED series {series_id}: {e}")
            return pd.DataFrame(columns=["date", "value"])

    def health_check(self) -> dict[str, Any]:
        """Check FRED source health.

        Returns:
            Health status dictionary.
        """
        if not self._config.enabled:
            return {"status": "disabled", "reason": "FRED_ENABLED not set"}

        if not FREDAPI_AVAILABLE:
            return {"status": "error", "reason": "fredapi package not installed"}

        if not self._config.api_key:
            return {"status": "error", "reason": "FRED_API_KEY not configured"}

        return {"status": "ready", "enabled": True}

    def list_series(self, limit: int = 10) -> list[dict[str, Any]]:
        """List popular FRED series (placeholder).

        Returns:
            List of series info.
        """
        if not self._config.enabled:
            return []

        popular_series = [
            {"series_id": "GDP", "title": "Gross Domestic Product"},
            {"series_id": "UNRATE", "title": "Unemployment Rate"},
            {"series_id": "CPIAUCSL", "title": "Consumer Price Index"},
            {"series_id": "FEDFUNDS", "title": "Federal Funds Rate"},
            {"series_id": "M2SL", "title": "M2 Money Supply"},
        ]
        return popular_series[:limit]


def create_fred_source() -> Optional[FredSource]:
    """Create FRED source if enabled.

    Returns:
        FredSource instance or None if not enabled.
    """
    config = FredConfig()
    if not config.enabled:
        return None

    try:
        return FredSource(config)
    except ImportError:
        return None