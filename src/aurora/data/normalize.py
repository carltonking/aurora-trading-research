"""Normalize market data into AURORA's standard OHLCV schema."""

from typing import Any

import pandas as pd

from aurora.data.exceptions import DataNormalizationError

STANDARD_OHLCV_COLUMNS = [
    "timestamp",
    "symbol",
    "open",
    "high",
    "low",
    "close",
    "adjusted_close",
    "volume",
    "source",
    "asset_type",
    "currency",
]

_COLUMN_MAP = {
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "adj close": "adjusted_close",
    "adjusted close": "adjusted_close",
    "adjusted_close": "adjusted_close",
    "volume": "volume",
    "date": "timestamp",
    "datetime": "timestamp",
    "timestamp": "timestamp",
    "index": "timestamp",
    "symbol": "symbol",
}


def normalize_ohlcv(
    df: pd.DataFrame,
    source: str,
    symbol: str | None = None,
    asset_type: str = "equity",
    currency: str = "USD",
) -> pd.DataFrame:
    """Normalize OHLCV data into the standard AURORA schema."""
    if not isinstance(df, pd.DataFrame):
        raise DataNormalizationError("Expected a pandas DataFrame.")
    if df.empty:
        return pd.DataFrame(columns=STANDARD_OHLCV_COLUMNS)

    normalized = df.copy()
    if not _has_timestamp_column(normalized):
        normalized = normalized.reset_index()

    normalized = normalized.rename(columns=_build_rename_map(normalized))

    if "symbol" not in normalized.columns:
        if symbol is None:
            raise DataNormalizationError("A symbol argument or symbol column is required.")
        normalized["symbol"] = symbol

    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = sorted(required - set(normalized.columns))
    if missing:
        raise DataNormalizationError(f"Missing required OHLCV columns: {', '.join(missing)}")

    if "adjusted_close" not in normalized.columns:
        normalized["adjusted_close"] = normalized["close"]

    normalized["timestamp"] = pd.to_datetime(normalized["timestamp"])
    normalized["symbol"] = normalized["symbol"].astype(str)
    normalized["source"] = source
    normalized["asset_type"] = asset_type
    normalized["currency"] = currency

    numeric_columns = ["open", "high", "low", "close", "adjusted_close", "volume"]
    for column in numeric_columns:
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")

    normalized = normalized[STANDARD_OHLCV_COLUMNS]
    normalized = normalized.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
    return normalized


def _lower_column_lookup(df: pd.DataFrame) -> dict[str, Any]:
    return {str(column).strip().lower(): column for column in df.columns}


def _has_timestamp_column(df: pd.DataFrame) -> bool:
    return any(_COLUMN_MAP.get(lowered) == "timestamp" for lowered in _lower_column_lookup(df))


def _build_rename_map(df: pd.DataFrame) -> dict[Any, str]:
    rename_map: dict[Any, str] = {}
    for lowered, original in _lower_column_lookup(df).items():
        if lowered in _COLUMN_MAP:
            rename_map[original] = _COLUMN_MAP[lowered]
    return rename_map


class DataNormalizer:
    """Compatibility wrapper around the normalization function."""

    def describe(self) -> str:
        """Return a short description of the component."""
        return "Normalizes market data into AURORA's standard OHLCV schema."
