"""Tests for FRED data source."""

import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from aurora.data.alternative.fred_source import (
    FredConfig,
    FredSource,
    create_fred_source,
    FREDAPI_AVAILABLE,
)


def test_fred_config_defaults() -> None:
    """Test default configuration."""
    config = FredConfig()

    assert config.enabled is False
    assert config.api_key is None


def test_fred_config_from_env() -> None:
    """Test loading config from environment."""
    original_enabled = os.environ.get("FRED_ENABLED")
    original_key = os.environ.get("FRED_API_KEY")

    try:
        os.environ["FRED_ENABLED"] = "true"
        os.environ["FRED_API_KEY"] = "test_key_123"

        config = FredConfig()

        assert config.enabled is True
        assert config.api_key == "test_key_123"
    finally:
        if original_enabled:
            os.environ["FRED_ENABLED"] = original_enabled
        else:
            del os.environ["FRED_ENABLED"]
        if original_key:
            os.environ["FRED_API_KEY"] = original_key
        else:
            del os.environ["FRED_API_KEY"]


def test_fred_config_repr_masks_key() -> None:
    """Test that repr masks the API key."""
    config = FredConfig(api_key="secret_key_123")

    repr_str = repr(config)

    assert "secret_key" not in repr_str
    assert "****" in repr_str


def test_fred_source_disabled_no_network() -> None:
    """Test that disabled source doesn't make network calls."""
    config = FredConfig(enabled=False)
    source = FredSource(config)

    assert source.enabled is False

    with pytest.raises(ValueError, match="not enabled"):
        source.fetch_series("GDP")


def test_fred_source_enabled_no_key() -> None:
    """Test that enabled source without key raises error."""
    config = FredConfig(enabled=True, api_key=None)
    source = FredSource(config)

    assert source.enabled is True

    if not FREDAPI_AVAILABLE:
        with pytest.raises(ImportError, match="fredapi"):
            source.fetch_series("GDP")
    else:
        with pytest.raises(ValueError, match="not configured"):
            source.fetch_series("GDP")


def test_fred_health_check_disabled() -> None:
    """Test health check when disabled."""
    config = FredConfig(enabled=False)
    source = FredSource(config)

    health = source.health_check()

    assert health["status"] == "disabled"


@patch.dict(os.environ, {"FRED_ENABLED": "true", "FRED_API_KEY": "test_key"})
def test_create_fred_source_enabled() -> None:
    """Test creating FredSource when enabled."""
    original_fredapi = FREDAPI_AVAILABLE

    try:
        import aurora.data.alternative.fred_source as fred_module

        original = fred_module.FREDAPI_AVAILABLE
        fred_module.FREDAPI_AVAILABLE = False

        try:
            result = create_fred_source()
            assert result is None
        finally:
            fred_module.FREDAPI_AVAILABLE = original
    finally:
        pass


def test_fred_list_series() -> None:
    """Test listing popular series."""
    config = FredConfig(enabled=True)
    source = FredSource(config)

    series = source.list_series(limit=3)

    assert len(series) == 3
    assert series[0]["series_id"] == "GDP"


def test_fred_source_missing_sdk() -> None:
    """Test that missing SDK raises ImportError."""
    config = FredConfig(enabled=True, api_key="test_key")

    with patch("aurora.data.alternative.fred_source.FREDAPI_AVAILABLE", False):
        with pytest.raises(ImportError, match="fredapi"):
            FredSource(config)