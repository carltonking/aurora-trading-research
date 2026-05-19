"""Feature generation for normalized OHLCV data."""

from copy import deepcopy
from typing import Any

import pandas as pd

from aurora.data.normalize import STANDARD_OHLCV_COLUMNS
from aurora.features.indicators import (
    atr,
    distance_from_moving_average,
    drawdown,
    log_return,
    macd,
    moving_average,
    rolling_high,
    rolling_low,
    rolling_volatility,
    rsi,
    simple_return,
    volume_change,
)

DEFAULT_FEATURE_CONFIG: dict[str, Any] = {
    "returns": {
        "simple_periods": [1, 5, 20],
        "log_periods": [1],
    },
    "moving_averages": [10, 20, 50, 200],
    "volatility_windows": [10, 20],
    "rsi_windows": [14],
    "macd": {
        "enabled": True,
        "fast": 12,
        "slow": 26,
        "signal": 9,
    },
    "atr_windows": [14],
    "drawdown": {
        "enabled": True,
    },
    "distance_ma_windows": [20, 50],
    "rolling_high_low_windows": [20, 50],
    "volume_change_periods": [1, 5],
}


def build_features(
    df: pd.DataFrame,
    config: dict[str, Any] | None = None,
    dropna: bool = False,
) -> pd.DataFrame:
    """Build deterministic research features from normalized OHLCV data."""
    _validate_input(df)
    feature_config = _merge_config(config)
    working = df.copy().sort_values(["symbol", "timestamp"])
    frames = [
        _build_symbol_features(symbol_df.copy(), feature_config)
        for _, symbol_df in working.groupby("symbol", sort=False)
    ]
    result = pd.concat(frames, ignore_index=True) if frames else working
    if dropna:
        result = result.dropna()
    return result.reset_index(drop=True)


def get_feature_columns(df: pd.DataFrame) -> list[str]:
    """Return feature columns, excluding standard OHLCV columns."""
    standard = set(STANDARD_OHLCV_COLUMNS)
    return [column for column in df.columns if column not in standard]


def _validate_input(df: pd.DataFrame) -> None:
    if not isinstance(df, pd.DataFrame):
        raise TypeError("build_features expects a pandas DataFrame.")
    missing = [column for column in STANDARD_OHLCV_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"Missing required OHLCV columns: {', '.join(missing)}")


def _merge_config(config: dict[str, Any] | None) -> dict[str, Any]:
    merged = deepcopy(DEFAULT_FEATURE_CONFIG)
    if not config:
        return merged
    for key, value in config.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key].update(value)
        else:
            merged[key] = value
    return merged


def _build_symbol_features(df: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    close = _main_close(df)

    for period in config["returns"]["simple_periods"]:
        df[f"return_{period}d"] = simple_return(close, periods=period)

    for period in config["returns"]["log_periods"]:
        df[f"log_return_{period}d"] = log_return(close, periods=period)

    for window in config["moving_averages"]:
        df[f"ma_{window}"] = moving_average(close, window=window)

    for window in config["volatility_windows"]:
        df[f"volatility_{window}"] = rolling_volatility(close, window=window)

    for window in config["rsi_windows"]:
        df[f"rsi_{window}"] = rsi(close, window=window)

    macd_config = config["macd"]
    if macd_config.get("enabled", True):
        macd_df = macd(
            close,
            fast=macd_config["fast"],
            slow=macd_config["slow"],
            signal=macd_config["signal"],
        )
        df[["macd", "macd_signal", "macd_hist"]] = macd_df

    for window in config["atr_windows"]:
        df[f"atr_{window}"] = atr(df, window=window)

    if config["drawdown"].get("enabled", True):
        df["drawdown"] = drawdown(close)

    for window in config["distance_ma_windows"]:
        df[f"dist_ma_{window}"] = distance_from_moving_average(close, window=window)

    for window in config["rolling_high_low_windows"]:
        df[f"rolling_high_{window}"] = rolling_high(close, window=window)
        df[f"rolling_low_{window}"] = rolling_low(close, window=window)

    for period in config["volume_change_periods"]:
        df[f"volume_change_{period}d"] = volume_change(df["volume"], periods=period)

    return df


def _main_close(df: pd.DataFrame) -> pd.Series:
    if "adjusted_close" in df.columns and not df["adjusted_close"].isna().all():
        return df["adjusted_close"]
    return df["close"]
