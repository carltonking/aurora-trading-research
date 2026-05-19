"""Feature engineering package."""

from aurora.features.build_features import DEFAULT_FEATURE_CONFIG, build_features, get_feature_columns
from aurora.features.indicators import (
    atr,
    distance_from_moving_average,
    drawdown,
    exponential_moving_average,
    log_return,
    macd,
    moving_average,
    rolling_high,
    rolling_low,
    rolling_mean,
    rolling_std,
    rolling_volatility,
    rsi,
    simple_return,
    true_range,
    volume_change,
)
from aurora.features.metadata import FeatureSetMetadata, create_feature_metadata

__all__ = [
    "DEFAULT_FEATURE_CONFIG",
    "FeatureSetMetadata",
    "atr",
    "build_features",
    "create_feature_metadata",
    "distance_from_moving_average",
    "drawdown",
    "exponential_moving_average",
    "get_feature_columns",
    "log_return",
    "macd",
    "moving_average",
    "rolling_high",
    "rolling_low",
    "rolling_mean",
    "rolling_std",
    "rolling_volatility",
    "rsi",
    "simple_return",
    "true_range",
    "volume_change",
]
