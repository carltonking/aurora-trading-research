"""News API data source.

Optional data source for financial news.
Placeholder implementation for news APIs.
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
class NewsConfig:
    """Configuration for News API source."""

    api_key: Optional[str] = None
    enabled: bool = False
    base_url: str = "https://newsapi.org/v2"

    def __post_init__(self) -> None:
        """Load config from environment if not provided."""
        if self.api_key is None:
            self.api_key = os.getenv("NEWS_API_KEY")
        if not self.enabled:
            self.enabled = os.getenv("NEWS_ENABLED", "false").lower() == "true"

    def __repr__(self) -> str:
        """Mask API key in repr."""
        key_mask = "****" if self.api_key else "None"
        return f"NewsConfig(enabled={self.enabled}, api_key={key_mask})"


class NewsSource:
    """News data source for financial headlines."""

    def __init__(self, config: Optional[NewsConfig] = None) -> None:
        """Initialize News source.

        Args:
            config: News configuration. If None, loads from env.
        """
        self._config = config or NewsConfig()

    @property
    def enabled(self) -> bool:
        """Check if source is enabled."""
        return self._config.enabled

    def fetch_news(
        self,
        ticker: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Fetch news articles for a ticker.

        Args:
            ticker: Stock ticker (e.g., "AAPL").
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).
            limit: Maximum number of articles.

        Returns:
            List of article dictionaries.

        Raises:
            ValueError: If source is disabled.
        """
        if not self._config.enabled:
            raise ValueError("News source is not enabled. Set NEWS_ENABLED=true.")

        logger.info(f"Fetching news for {ticker}")

        placeholder_articles = [
            {
                "title": f"{ticker} Reports Quarterly Earnings",
                "description": f"{ticker} announced quarterly results...",
                "published_at": "2024-01-15T10:00:00Z",
                "source": "placeholder",
                "url": f"https://example.com/news/{ticker.lower()}",
            },
            {
                "title": f"Analyst Raises Price Target for {ticker}",
                "description": f"Leading analyst upgrades {ticker}...",
                "published_at": "2024-01-14T14:30:00Z",
                "source": "placeholder",
                "url": f"https://example.com/news/{ticker.lower()}_upgrade",
            },
        ]

        return placeholder_articles[:limit]

    def health_check(self) -> dict[str, Any]:
        """Check News source health.

        Returns:
            Health status dictionary.
        """
        if not self._config.enabled:
            return {"status": "disabled", "reason": "NEWS_ENABLED not set"}

        if not self._config.api_key:
            return {"status": "warning", "reason": "NEWS_API_KEY not set (using placeholder data)"}

        return {"status": "ready", "enabled": True}


def create_news_source() -> Optional[NewsSource]:
    """Create News source if enabled.

    Returns:
        NewsSource instance or None if not enabled.
    """
    config = NewsConfig()
    if not config.enabled:
        return None
    return NewsSource(config)