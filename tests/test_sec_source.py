"""Tests for SEC EDGAR data source."""

import os
import pytest

from aurora.data.alternative.sec_source import (
    SecConfig,
    SecSource,
    create_sec_source,
)


def test_sec_config_defaults() -> None:
    """Test default configuration."""
    config = SecConfig()

    assert config.enabled is False
    assert config.user_agent is None


def test_sec_config_from_env() -> None:
    """Test loading config from environment."""
    original_enabled = os.environ.get("SEC_ENABLED")
    original_ua = os.environ.get("SEC_USER_AGENT")

    try:
        os.environ["SEC_ENABLED"] = "true"
        os.environ["SEC_USER_AGENT"] = "test@example.com"

        config = SecConfig()

        assert config.enabled is True
        assert config.user_agent == "test@example.com"
    finally:
        if original_enabled:
            os.environ["SEC_ENABLED"] = original_enabled
        else:
            del os.environ["SEC_ENABLED"]
        if original_ua:
            os.environ["SEC_USER_AGENT"] = original_ua
        else:
            del os.environ["SEC_USER_AGENT"]


def test_sec_config_repr_masks_ua() -> None:
    """Test that repr masks the user agent."""
    config = SecConfig(user_agent="secret@example.com")

    repr_str = repr(config)

    assert "secret" not in repr_str
    assert "****" in repr_str


def test_sec_source_disabled() -> None:
    """Test disabled source doesn't make network calls."""
    config = SecConfig(enabled=False)
    source = SecSource(config)

    assert source.enabled is False

    with pytest.raises(ValueError, match="not enabled"):
        source.fetch_filings("AAPL")


def test_sec_source_enabled() -> None:
    """Test enabled source returns placeholder data."""
    config = SecConfig(enabled=True)
    source = SecSource(config)

    assert source.enabled is True

    filings = source.fetch_filings("AAPL", "10-K", limit=3)

    assert len(filings) <= 3
    assert filings[0]["ticker"] == "AAPL"
    assert filings[0]["form_type"] == "10-K"


def test_sec_source_extract_sentiment() -> None:
    """Test sentiment extraction returns placeholder."""
    config = SecConfig(enabled=True)
    source = SecSource(config)

    sentiment = source.extract_sentiment("AAPL")

    assert sentiment["ticker"] == "AAPL"
    assert sentiment["sentiment"] == "neutral"
    assert sentiment["source"] == "placeholder"


def test_sec_health_check_disabled() -> None:
    """Test health check when disabled."""
    config = SecConfig(enabled=False)
    source = SecSource(config)

    health = source.health_check()

    assert health["status"] == "disabled"


def test_sec_health_check_enabled() -> None:
    """Test health check when enabled."""
    config = SecConfig(enabled=True)
    source = SecSource(config)

    health = source.health_check()

    assert health["status"] == "ready"


def test_create_sec_source_disabled() -> None:
    """Test create returns None when disabled."""
    result = create_sec_source()

    assert result is None


def test_create_sec_source_enabled() -> None:
    """Test create returns source when enabled."""
    original = os.environ.get("SEC_ENABLED")

    try:
        os.environ["SEC_ENABLED"] = "true"

        result = create_sec_source()

        assert result is not None
        assert isinstance(result, SecSource)
    finally:
        if original:
            os.environ["SEC_ENABLED"] = original
        else:
            del os.environ["SEC_ENABLED"]