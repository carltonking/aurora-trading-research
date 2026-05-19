"""Model management package."""

from aurora.models.labels import create_forward_return_label
from aurora.models.predict import PredictionResult, predict_with_model
from aurora.models.registry import (
    list_model_artifacts,
    load_model_artifact,
    save_model_artifact,
)
from aurora.models.train import (
    DEFAULT_MODEL_CONFIG,
    TrainingResult,
    select_feature_columns,
    train_baseline_classifier,
)

__all__ = [
    "DEFAULT_MODEL_CONFIG",
    "PredictionResult",
    "TrainingResult",
    "create_forward_return_label",
    "list_model_artifacts",
    "load_model_artifact",
    "predict_with_model",
    "save_model_artifact",
    "select_feature_columns",
    "train_baseline_classifier",
]
