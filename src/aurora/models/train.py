"""Baseline supervised model training for research workflows."""

from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
import uuid

import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score

from aurora.models.exceptions import ModelTrainingError
from aurora.models.labels import create_forward_return_label

DEFAULT_MODEL_CONFIG: dict[str, Any] = {
    "model_type": "random_forest",
    "label": {
        "horizon": 5,
        "threshold": 0.0,
        "price_col": "adjusted_close",
        "label_col": "target",
    },
    "training": {
        "test_size": 0.25,
        "min_rows": 100,
        "random_state": 42,
    },
    "features": {
        "exclude_columns": [
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
            "target",
        ],
        "include_prefixes": [
            "return_",
            "log_return_",
            "ma_",
            "volatility_",
            "rsi_",
            "macd",
            "atr_",
            "drawdown",
            "dist_ma_",
            "rolling_high_",
            "rolling_low_",
            "volume_change_",
        ],
    },
}


@dataclass
class TrainingResult:
    """Result metadata from a baseline training run."""

    model_id: str
    model_type: str
    trained_at: str
    row_count: int
    feature_count: int
    features: list[str]
    metrics: dict[str, float | int]
    label_config: dict[str, Any]
    model_path: str | None = None


def select_feature_columns(df: pd.DataFrame, config: dict[str, Any] | None = None) -> list[str]:
    """Select numeric feature columns using configured prefixes and exclusions."""
    model_config = _merge_config(config)
    feature_config = model_config["features"]
    exclude = set(feature_config["exclude_columns"])
    prefixes = tuple(feature_config["include_prefixes"])

    columns = []
    for column in df.columns:
        if column in exclude or not column.startswith(prefixes):
            continue
        if pd.api.types.is_numeric_dtype(df[column]):
            columns.append(column)
    return columns


def train_baseline_classifier(
    feature_df: pd.DataFrame,
    config: dict[str, Any] | None = None,
) -> tuple[object, TrainingResult]:
    """Train a deterministic RandomForest baseline classifier."""
    model_config = _merge_config(config)
    if model_config["model_type"] != "random_forest":
        raise ModelTrainingError("Only random_forest is supported in the baseline trainer.")

    label_config = model_config["label"]
    label_col = label_config["label_col"]
    labeled = create_forward_return_label(feature_df, **label_config)
    feature_columns = select_feature_columns(labeled, model_config)
    if not feature_columns:
        raise ModelTrainingError("No numeric feature columns were selected for training.")

    training_data = labeled.dropna(subset=[*feature_columns, label_col]).copy()
    min_rows = int(model_config["training"]["min_rows"])
    if len(training_data) < min_rows:
        raise ModelTrainingError(
            f"Not enough rows to train: {len(training_data)} available, {min_rows} required."
        )

    training_data = training_data.sort_values(["timestamp", "symbol"]).reset_index(drop=True)
    train_df, test_df = _chronological_split(training_data, model_config["training"]["test_size"])

    model = RandomForestClassifier(
        n_estimators=100,
        random_state=model_config["training"]["random_state"],
        n_jobs=1,
    )
    model.fit(train_df[feature_columns], train_df[label_col].astype(int))

    predictions = model.predict(test_df[feature_columns])
    truth = test_df[label_col].astype(int)
    metrics: dict[str, float | int] = {
        "accuracy": float(accuracy_score(truth, predictions)),
        "precision": float(precision_score(truth, predictions, zero_division=0)),
        "recall": float(recall_score(truth, predictions, zero_division=0)),
        "f1": float(f1_score(truth, predictions, zero_division=0)),
        "train_rows": int(len(train_df)),
        "test_rows": int(len(test_df)),
    }

    trained_at = datetime.now(UTC).isoformat()
    result = TrainingResult(
        model_id=f"model_{trained_at.replace(':', '').replace('+', 'z')}_{uuid.uuid4().hex[:8]}",
        model_type=model_config["model_type"],
        trained_at=trained_at,
        row_count=len(training_data),
        feature_count=len(feature_columns),
        features=feature_columns,
        metrics=metrics,
        label_config=deepcopy(label_config),
    )
    return model, result


def _chronological_split(df: pd.DataFrame, test_size: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not 0 < test_size < 1:
        raise ModelTrainingError("training.test_size must be between 0 and 1.")
    split_index = int(len(df) * (1 - test_size))
    if split_index <= 0 or split_index >= len(df):
        raise ModelTrainingError("Chronological split produced an empty train or test set.")
    return df.iloc[:split_index], df.iloc[split_index:]


def _merge_config(config: dict[str, Any] | None) -> dict[str, Any]:
    merged = deepcopy(DEFAULT_MODEL_CONFIG)
    if not config:
        return merged
    for key, value in config.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            for nested_key, nested_value in value.items():
                if isinstance(nested_value, dict) and isinstance(merged[key].get(nested_key), dict):
                    merged[key][nested_key].update(nested_value)
                else:
                    merged[key][nested_key] = nested_value
        else:
            merged[key] = value
    return merged
