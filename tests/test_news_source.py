"""Tests for News API data source."""

import os
import pytest

from aurora.data.alternative.news_source import (
    NewsConfig,
    NewsSource,
    create_news_source,
)


def test_news_config_defaults() -> None:
    """Test default configuration."""
    config = NewsConfig()

    assert config.enabled is False
    assert config.api_key is None


def test_news_config_from_env() -> None:
    """Test loading config from environment."""
    original_enabled = os.environ.get("NEWS_ENABLED")
    original_key = os.environ.get("NEWS_API_KEY")

    try:
        os.environ["NEWS_ENABLED"] = "true"
        os.environ["NEWS_API_KEY"] = "test_api_key_123"

        config = NewsConfig()

        assert config.enabled is True
        assert config.api_key == "test_api_key_123"
    finally:
        if original_enabled:
            os.environ["NEWS_ENABLED"] = original_enabled
        else:
            del os.environ["NEWS_ENABLED"]
        if original_key:
            os.environ["NEWS_API_KEY"] = original_key
        else:
            del os.environ["NEWS_API_KEY"]


def test_news_config_repr_masks_key() -> None:
    """Test that repr masks the API key."""
    config = NewsConfig(api_key="secret_key_123")

    repr_str = repr(config)

    assert "secret_key" not in repr_str
    assert "****" in repr_str


def test_news_source_disabled() -> None:
    """Test disabled source doesn't make network calls."""
    config = NewsConfig(enabled=False)
    source = NewsSource(config)

    assert source.enabled is False

    with pytest.raises(ValueError, match="not enabled"):
        source.fetch_news("AAPL")


def test_news_source_enabled() -> None:
    """Test enabled source returns placeholder data."""
    config = NewsConfig(enabled=True)
    source = NewsSource(config)

    assert source.enabled is True

    articles = source.fetch_news("AAPL", limit=5)

    assert len(articles) <= 5
    assert articles[0]["title"] is not None


def test_news_source_health_check_disabled() -> None:
    """Test health check when disabled."""
    config = NewsConfig(enabled=False)
    source = NewsSource(config)

    health = source.health_check()

    assert health["status"] == "disabled"


def test_news_source_health_check_enabled_no_key() -> None:
    """Test health check when enabled but no API key."""
    config = NewsConfig(enabled=True, api_key=None)
    source = NewsSource(config)

    health = source.health_check()

    assert health["status"] == "warning"
    assert "placeholder" in health["reason"]


def test_news_source_health_check_enabled_with_key() -> None:
    """Test health check when enabled with API key."""
    config = NewsConfig(enabled=True, api_key="test_key")
    source = NewsSource(config)

    health = source.health_check()

    assert health["status"] == "ready"


def test_create_news_source_disabled() -> None:
    """Test create returns None when disabled."""
    result = create_news_source()

    assert result is None


def test_create_news_source_enabled() -> None:
    """Test create returns source when enabled."""
    original = os.environ.get("NEWS_ENABLED")

    try:
        os.environ["NEWS_ENABLED"] = "true"

        result = create_news_source()

        assert result is not None
        assert isinstance(result, NewsSource)
    finally:
        if original:
            os.environ["NEWS_ENABLED"] = original
        else:
            del os.environ["NEWS_ENABLED"]