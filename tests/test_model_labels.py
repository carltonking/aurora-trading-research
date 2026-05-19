import pandas as pd
import pytest

from aurora.models.exceptions import LabelGenerationError
from aurora.models.labels import create_forward_return_label


def _price_df() -> pd.DataFrame:
    rows = []
    for symbol in ["AAPL", "MSFT"]:
        for i in range(5):
            rows.append(
                {
                    "timestamp": pd.Timestamp("2024-01-01") + pd.Timedelta(days=i),
                    "symbol": symbol,
                    "adjusted_close": 100.0 + i,
                }
            )
    return pd.DataFrame(rows)


def test_labels_are_created_per_symbol() -> None:
    result = create_forward_return_label(_price_df(), horizon=1)

    first_by_symbol = result.groupby("symbol", sort=False).head(1)
    assert (first_by_symbol["future_return_1d"] > 0).all()
    assert first_by_symbol["target"].tolist() == [1.0, 1.0]


def test_last_horizon_rows_per_symbol_are_nan() -> None:
    result = create_forward_return_label(_price_df(), horizon=2)

    tail = result.groupby("symbol", sort=False).tail(2)
    assert tail["target"].isna().all()
    assert tail["future_return_2d"].isna().all()


def test_invalid_horizon_raises_value_error() -> None:
    with pytest.raises(ValueError):
        create_forward_return_label(_price_df(), horizon=0)


def test_missing_columns_raise_label_generation_error() -> None:
    with pytest.raises(LabelGenerationError):
        create_forward_return_label(pd.DataFrame({"symbol": ["AAPL"]}))
