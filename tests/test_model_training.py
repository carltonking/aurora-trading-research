import numpy as np
import pandas as pd
import pytest

from aurora.models.exceptions import ModelTrainingError
from aurora.models.train import TrainingResult, select_feature_columns, train_baseline_classifier


def _feature_df(rows: int = 150, include_features: bool = True) -> pd.DataFrame:
    timestamps = pd.date_range("2024-01-01", periods=rows, freq="D")
    trend = np.arange(rows, dtype=float)
    cycle = np.sin(np.arange(rows) / 3)
    close = 100 + trend * 0.05 + cycle
    df = pd.DataFrame(
        {
            "timestamp": timestamps,
            "symbol": ["AAPL"] * rows,
            "open": close - 0.2,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "adjusted_close": close,
            "volume": 1000 + trend,
            "source": ["test"] * rows,
            "asset_type": ["equity"] * rows,
            "currency": ["USD"] * rows,
        }
    )
    if include_features:
        df["return_1d"] = pd.Series(close).pct_change().fillna(0).to_numpy()
        df["ma_5"] = pd.Series(close).rolling(5, min_periods=1).mean().to_numpy()
        df["volatility_5"] = pd.Series(close).pct_change().rolling(5, min_periods=1).std().fillna(0).to_numpy()
        df["rsi_14"] = 50 + cycle * 10
        df["macd"] = cycle
        df["atr_14"] = 1.0
        df["drawdown"] = 0.0
        df["volume_change_1d"] = df["volume"].pct_change().fillna(0)
    return df


def test_select_feature_columns_returns_expected_features() -> None:
    df = _feature_df()

    features = select_feature_columns(df)

    assert "return_1d" in features
    assert "ma_5" in features
    assert "timestamp" not in features
    assert "adjusted_close" not in features


def test_train_baseline_classifier_returns_model_and_result() -> None:
    model, result = train_baseline_classifier(_feature_df())

    assert hasattr(model, "predict")
    assert isinstance(result, TrainingResult)
    assert result.model_type == "random_forest"
    assert result.feature_count > 0
    assert {"accuracy", "precision", "recall", "f1"}.issubset(result.metrics)


def test_not_enough_rows_raises_model_training_error() -> None:
    with pytest.raises(ModelTrainingError):
        train_baseline_classifier(_feature_df(rows=20))


def test_no_feature_columns_raises_model_training_error() -> None:
    with pytest.raises(ModelTrainingError):
        train_baseline_classifier(_feature_df(include_features=False))
