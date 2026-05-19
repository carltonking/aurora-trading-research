"""Tests for intraday data support."""

import numpy as np
import pandas as pd
import pytest

from aurora.data.intraday_helpers import (
    convert_interval_to_holding_period,
    get_bars_per_day,
    get_interval_frequency,
    normalize_timestamp_to_utc,
    resample_to_higher_timeframe,
    validate_intraday_interval,
)


def test_validate_intraday_interval_valid() -> None:
    """Test validating valid intervals."""
    assert validate_intraday_interval("1m") is True
    assert validate_intraday_interval("5m") is True
    assert validate_intraday_interval("15m") is True
    assert validate_intraday_interval("30m") is True
    assert validate_intraday_interval("1h") is True
    assert validate_intraday_interval("1d") is True


def test_validate_intraday_interval_invalid() -> None:
    """Test validating invalid intervals."""
    assert validate_intraday_interval("2m") is False
    assert validate_intraday_interval("10m") is False
    assert validate_intraday_interval("unknown") is False


def test_get_interval_frequency() -> None:
    """Test mapping intervals to pandas frequencies."""
    assert get_interval_frequency("1m") == "min"
    assert get_interval_frequency("5m") == "5min"
    assert get_interval_frequency("15m") == "15min"
    assert get_interval_frequency("30m") == "30min"
    assert get_interval_frequency("1h") == "h"
    assert get_interval_frequency("1d") == "D"


def test_get_interval_frequency_invalid() -> None:
    """Test invalid interval raises error."""
    with pytest.raises(ValueError, match="Unknown interval"):
        get_interval_frequency("invalid")


def test_get_bars_per_day() -> None:
    """Test bars per day calculation."""
    assert get_bars_per_day("1m") == 390
    assert get_bars_per_day("5m") == 78
    assert get_bars_per_day("15m") == 26
    assert get_bars_per_day("30m") == 13
    assert get_bars_per_day("1h") == 7.5
    assert get_bars_per_day("1d") == 1


def test_convert_interval_to_holding_period() -> None:
    """Test converting holding period to bars."""
    assert convert_interval_to_holding_period("1d", 1) == 1
    assert convert_interval_to_holding_period("1h", 1) == 7
    assert convert_interval_to_holding_period("5m", 1) == 78
    assert convert_interval_to_holding_period("1m", 1) == 390


def test_resample_to_higher_timeframe() -> None:
    """Test resampling intraday data to higher timeframe."""
    dates = pd.date_range("2020-01-01 09:00", periods=60, freq="min")
    data = pd.DataFrame({
        "open": np.random.randn(60).cumsum() + 100,
        "high": np.random.randn(60).cumsum() + 102,
        "low": np.random.randn(60).cumsum() + 98,
        "close": np.random.randn(60).cumsum() + 100,
        "volume": np.random.randint(1000, 10000, 60),
    }, index=dates)

    resampled = resample_to_higher_timeframe(data, "1h")

    assert len(resampled) == 1
    assert "open" in resampled.columns
    assert "high" in resampled.columns


def test_resample_empty_dataframe() -> None:
    """Test resampling empty DataFrame."""
    data = pd.DataFrame()
    result = resample_to_higher_timeframe(data, "1h")
    assert result.empty


def test_normalize_timestamp_to_utc() -> None:
    """Test normalizing timestamps to UTC."""
    dates = pd.date_range("2020-01-01", periods=5, freq="D")
    data = pd.DataFrame({"close": [100, 101, 102, 103, 104]}, index=dates)

    result = normalize_timestamp_to_utc(data)

    assert result.index.tz is not None
    assert str(result.index.tz) == "UTC"


def test_normalize_timestamp_already_utc() -> None:
    """Test normalizing already UTC timestamps."""
    dates = pd.date_range("2020-01-01", periods=5, freq="D", tz="UTC")
    data = pd.DataFrame({"close": [100, 101, 102, 103, 104]}, index=dates)

    result = normalize_timestamp_to_utc(data)

    assert str(result.index.tz) == "UTC"


def test_backtest_config_interval_periods() -> None:
    """Test that BacktestConfig calculates periods_per_year from interval."""
    from aurora.backtesting.engine import BacktestConfig

    config_daily = BacktestConfig(interval="1d")
    assert config_daily.periods_per_year == 252

    config_hourly = BacktestConfig(interval="1h")
    assert config_hourly.periods_per_year == 1890

    config_5m = BacktestConfig(interval="5m")
    assert config_5m.periods_per_year == 19656


def test_backtest_config_explicit_periods() -> None:
    """Test that explicit periods_per_year overrides interval calculation."""
    from aurora.backtesting.engine import BacktestConfig

    config = BacktestConfig(interval="1h", periods_per_year=1000)
    assert config.periods_per_year == 1000