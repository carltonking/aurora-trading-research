"""Supervised label generation for research models."""

import numpy as np
import pandas as pd

from aurora.models.exceptions import LabelGenerationError


def create_forward_return_label(
    df: pd.DataFrame,
    horizon: int = 5,
    threshold: float = 0.0,
    price_col: str = "adjusted_close",
    label_col: str = "target",
) -> pd.DataFrame:
    """Create a binary label from future per-symbol returns."""
    if horizon <= 0:
        raise ValueError("horizon must be greater than 0.")

    required = {"symbol", "timestamp", price_col}
    missing = sorted(required - set(df.columns))
    if missing:
        raise LabelGenerationError(f"Missing required columns for labels: {', '.join(missing)}")

    labeled = df.copy().sort_values(["symbol", "timestamp"]).reset_index(drop=True)
    future_return_col = f"future_return_{horizon}d"
    labeled[future_return_col] = labeled.groupby("symbol", sort=False)[price_col].transform(
        lambda price: price.shift(-horizon) / price - 1
    )
    labeled[label_col] = np.where(labeled[future_return_col] > threshold, 1.0, 0.0)
    labeled.loc[labeled[future_return_col].isna(), label_col] = np.nan
    return labeled
