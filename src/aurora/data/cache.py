"""CSV cache utilities for normalized market data."""

from pathlib import Path
import re

import pandas as pd


def get_cache_dir(base_dir: str | Path = "data/cache") -> Path:
    """Return the cache directory, creating it if needed."""
    path = Path(base_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_key(
    source: str,
    symbols: list[str],
    start: str,
    end: str | None,
    interval: str,
) -> str:
    """Build a deterministic filesystem-safe cache key."""
    normalized_symbols = "-".join(sorted(symbol.strip().upper() for symbol in symbols if symbol.strip()))
    raw_key = f"{source}_{normalized_symbols}_{start}_{end or 'none'}_{interval}".lower()
    return re.sub(r"[^a-z0-9_.-]+", "-", raw_key).strip("-")


def save_market_data(
    df: pd.DataFrame,
    key: str,
    base_dir: str | Path = "data/cache",
) -> Path:
    """Save normalized market data to a CSV cache file."""
    path = get_cache_dir(base_dir) / f"{key}.csv"
    df.to_csv(path, index=False)
    return path


def load_market_data(
    key: str,
    base_dir: str | Path = "data/cache",
) -> pd.DataFrame | None:
    """Load normalized market data from CSV cache."""
    path = Path(base_dir) / f"{key}.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df
