"""Intraday data utilities.

This module provides research-only intraday data handling. No live trading, no broker calls.
"""

from typing import Any

import pandas as pd


VALID_INTERVALS = {
    "1m": "1 minute",
    "5m": "5 minutes",
    "15m": "15 minutes",
    "30m": "30 minutes",
    "1h": "1 hour",
    "1d": "1 day",
    "1wk": "1 week",
    "1mo": "1 month",
}


def validate_intraday_interval(interval: str) -> bool:
    """Validate if an interval string is supported.

    Args:
        interval: An interval string like "1m", "5m", "1h", "1d".

    Returns:
        True if valid, False otherwise.
    """
    return interval in VALID_INTERVALS


def get_interval_frequency(interval: str) -> str:
    """Get the pandas frequency string for an interval.

    Args:
        interval: An interval string like "1m", "5m", "1h".

    Returns:
        Pandas frequency string.

    Raises:
        ValueError: If interval is not recognized.
    """
    mapping = {
        "1m": "min",
        "5m": "5min",
        "15m": "15min",
        "30m": "30min",
        "1h": "h",
        "1d": "D",
        "1wk": "W",
        "1mo": "MS",
    }

    if interval not in mapping:
        raise ValueError(f"Unknown interval: {interval}. Valid: {list(mapping.keys())}")

    return mapping[interval]


def resample_to_higher_timeframe(
    data: pd.DataFrame,
    target_interval: str,
    price_columns: list[str] | None = None,
) -> pd.DataFrame:
    """Resample intraday data to a higher timeframe.

    Args:
        data: DataFrame with OHLCV data and DatetimeIndex.
        target_interval: Target interval string (e.g., "1h", "4h", "1d").
        price_columns: Columns to resample. Defaults to ['open', 'high', 'low', 'close', 'volume'].

    Returns:
        DataFrame resampled to the target timeframe.
    """
    if price_columns is None:
        price_columns = ["open", "high", "low", "close", "volume"]

    available_cols = [c for c in price_columns if c in data.columns]
    if not available_cols:
        return data

    freq = get_interval_frequency(target_interval)

    resampled = data[available_cols].resample(freq).agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    })

    if "volume" in available_cols and "volume" not in resampled.columns:
        resampled["volume"] = data["volume"].resample(freq).sum()

    return resampled.dropna()


def normalize_timestamp_to_utc(data: pd.DataFrame) -> pd.DataFrame:
    """Normalize DataFrame timestamps to UTC and make timezone-aware.

    Args:
        data: DataFrame with datetime index.

    Returns:
        DataFrame with UTC timezone-aware index.
    """
    if data.empty:
        return data

    result = data.copy()

    if result.index.tz is None:
        result.index = result.index.tz_localize("UTC")
    elif str(result.index.tz) != "UTC":
        result.index = result.index.tz_convert("UTC")

    return result


def get_bars_per_day(interval: str) -> float:
    """Estimate the number of bars per trading day for an interval.

    Args:
        interval: Interval string.

    Returns:
        Approximate bars per day.
    """
    bars_per_day = {
        "1m": 390,
        "5m": 78,
        "15m": 26,
        "30m": 13,
        "1h": 7.5,
        "1d": 1,
    }

    return bars_per_day.get(interval, 1)


def convert_interval_to_holding_period(interval: str, target_days: int = 1) -> int:
    """Convert a target holding period in days to bars for an interval.

    Args:
        interval: Interval string.
        target_days: Number of calendar days to hold.

    Returns:
        Number of bars to hold.
    """
    bars_per_day_val = get_bars_per_day(interval)
    return int(target_days * bars_per_day_val)