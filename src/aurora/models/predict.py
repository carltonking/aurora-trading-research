"""Prediction helpers for trained research models."""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from aurora.models.exceptions import AuroraModelError


@dataclass(frozen=True)
class PredictionResult:
    """Summary of a prediction run."""

    row_count: int
    prediction_count: int
    positive_signal_count: int
    probability_column: str
    prediction_column: str


def predict_with_model(
    model: object,
    feature_df: pd.DataFrame,
    feature_columns: list[str],
    prediction_col: str = "prediction",
    probability_col: str = "prediction_probability",
) -> tuple[pd.DataFrame, PredictionResult]:
    """Generate model predictions for rows with complete feature values."""
    missing = [column for column in feature_columns if column not in feature_df.columns]
    if missing:
        raise AuroraModelError(f"Missing feature columns for prediction: {', '.join(missing)}")

    output = feature_df.copy()
    output[prediction_col] = np.nan
    output[probability_col] = np.nan
    if not feature_columns:
        raise AuroraModelError("At least one feature column is required for prediction.")

    prediction_frame = output.dropna(subset=feature_columns)
    if prediction_frame.empty:
        result = PredictionResult(
            row_count=len(output),
            prediction_count=0,
            positive_signal_count=0,
            probability_column=probability_col,
            prediction_column=prediction_col,
        )
        return output, result

    predictions = model.predict(prediction_frame[feature_columns])
    output.loc[prediction_frame.index, prediction_col] = predictions

    probabilities = _class_one_probabilities(model, prediction_frame[feature_columns])
    if probabilities is not None:
        output.loc[prediction_frame.index, probability_col] = probabilities

    result = PredictionResult(
        row_count=len(output),
        prediction_count=len(prediction_frame),
        positive_signal_count=int((pd.Series(predictions) == 1).sum()),
        probability_column=probability_col,
        prediction_column=prediction_col,
    )
    return output, result


def _class_one_probabilities(model: object, features: pd.DataFrame) -> np.ndarray | None:
    if not hasattr(model, "predict_proba"):
        return None
    probabilities = model.predict_proba(features)
    classes = list(getattr(model, "classes_", []))
    if 1 not in classes:
        return None
    return probabilities[:, classes.index(1)]
