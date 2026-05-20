"""SEC EDGAR data source.

Optional data source for SEC filings.
Placeholder implementation using sec-api or edgartools.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


@dataclass
class SecConfig:
    """Configuration for SEC EDGAR source."""

    user_agent: Optional[str] = None
    enabled: bool = False

    def __post_init__(self) -> None:
        """Load config from environment if not provided."""
        if self.user_agent is None:
            self.user_agent = os.getenv("SEC_USER_AGENT")
        if not self.enabled:
            self.enabled = os.getenv("SEC_ENABLED", "false").lower() == "true"

    def __repr__(self) -> str:
        """Mask user agent in repr."""
        ua_mask = "****" if self.user_agent else "None"
        return f"SecConfig(enabled={self.enabled}, user_agent={ua_mask})"


class SecSource:
    """SEC EDGAR data source for filings and sentiment."""

    def __init__(self, config: Optional[SecConfig] = None) -> None:
        """Initialize SEC source.

        Args:
            config: SEC configuration. If None, loads from env.
        """
        self._config = config or SecConfig()

    @property
    def enabled(self) -> bool:
        """Check if source is enabled."""
        return self._config.enabled

    def fetch_filings(
        self,
        ticker: str,
        form_type: str = "10-K",
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Fetch SEC filings for a ticker.

        Args:
            ticker: Stock ticker (e.g., "AAPL").
            form_type: Form type to filter (e.g., "10-K", "10-Q").
            limit: Maximum number of filings to return.

        Returns:
            List of filing metadata dictionaries.

        Raises:
            ValueError: If source is disabled.
        """
        if not self._config.enabled:
            raise ValueError("SEC source is not enabled. Set SEC_ENABLED=true.")

        logger.info(f"Fetching {form_type} filings for {ticker}")

        return [
            {
                "ticker": ticker,
                "form_type": form_type,
                "filed_date": "2024-01-01",
                "accepted_date": "2024-01-02",
                "accession_number": f"000{ticker.lower()}2024-01",
            }
        ][:limit]

    def extract_sentiment(self, ticker: str) -> dict[str, Any]:
        """Extract sentiment from recent filings (placeholder).

        Args:
            ticker: Stock ticker.

        Returns:
            Sentiment analysis dictionary.

        Raises:
            ValueError: If source is disabled.
        """
        if not self._config.enabled:
            raise ValueError("SEC source is not enabled. Set SEC_ENABLED=true.")

        return {
            "ticker": ticker,
            "sentiment": "neutral",
            "positive_words": 0,
            "negative_words": 0,
            "source": "placeholder",
            "note": "Actual sentiment extraction requires full NLP pipeline",
        }

    def health_check(self) -> dict[str, Any]:
        """Check SEC source health.

        Returns:
            Health status dictionary.
        """
        if not self._config.enabled:
            return {"status": "disabled", "reason": "SEC_ENABLED not set"}

        return {"status": "ready", "enabled": True}


def create_sec_source() -> Optional[SecSource]:
    """Create SEC source if enabled.

    Returns:
        SecSource instance or None if not enabled.
    """
    config = SecConfig()
    if not config.enabled:
        return None
    return SecSource(config)