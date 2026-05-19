import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import RandomForestClassifier

from aurora.models.exceptions import AuroraModelError
from aurora.models.predict import predict_with_model


def _trained_model() -> RandomForestClassifier:
    x = pd.DataFrame({"return_1d": [-0.2, -0.1, 0.1, 0.2], "ma_5": [1.0, 1.1, 1.2, 1.3]})
    y = np.array([0, 0, 1, 1])
    model = RandomForestClassifier(n_estimators=10, random_state=42)
    model.fit(x, y)
    return model


def test_predict_with_model_adds_prediction_and_probability_columns() -> None:
    feature_df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=3),
            "symbol": ["AAPL", "AAPL", "AAPL"],
            "return_1d": [-0.1, 0.2, np.nan],
            "ma_5": [1.0, 1.3, 1.4],
        }
    )

    output, result = predict_with_model(_trained_model(), feature_df, ["return_1d", "ma_5"])

    assert "prediction" in output.columns
    assert "prediction_probability" in output.columns
    assert result.row_count == 3
    assert result.prediction_count == 2
    assert output["prediction"].notna().sum() == 2
    assert output["prediction_probability"].notna().sum() == 2


def test_missing_feature_columns_raise_aurora_model_error() -> None:
    with pytest.raises(AuroraModelError):
        predict_with_model(_trained_model(), pd.DataFrame({"return_1d": [0.1]}), ["return_1d", "ma_5"])
