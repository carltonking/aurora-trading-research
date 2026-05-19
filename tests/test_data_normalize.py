import pandas as pd
import pytest

from aurora.data.exceptions import DataNormalizationError
from aurora.data.normalize import STANDARD_OHLCV_COLUMNS, normalize_ohlcv


def test_normalize_yfinance_style_single_symbol_dataframe() -> None:
    raw = pd.DataFrame(
        {
            "Open": [100.0, 101.0],
            "High": [102.0, 103.0],
            "Low": [99.0, 100.0],
            "Close": [101.0, 102.0],
            "Adj Close": [100.5, 101.5],
            "Volume": [1000, 1100],
        },
        index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
    )

    result = normalize_ohlcv(raw, source="yfinance", symbol="AAPL")

    assert list(result.columns) == STANDARD_OHLCV_COLUMNS
    assert result["symbol"].tolist() == ["AAPL", "AAPL"]
    assert result["source"].unique().tolist() == ["yfinance"]
    assert result["adjusted_close"].tolist() == [100.5, 101.5]
    assert pd.api.types.is_datetime64_any_dtype(result["timestamp"])


def test_adjusted_close_falls_back_to_close() -> None:
    raw = pd.DataFrame(
        {
            "Date": ["2024-01-02"],
            "Open": [100.0],
            "High": [102.0],
            "Low": [99.0],
            "Close": [101.0],
            "Volume": [1000],
        }
    )

    result = normalize_ohlcv(raw, source="yfinance", symbol="AAPL")

    assert result.loc[0, "adjusted_close"] == result.loc[0, "close"]


def test_missing_required_columns_raises() -> None:
    raw = pd.DataFrame({"Date": ["2024-01-02"], "Open": [100.0]})

    with pytest.raises(DataNormalizationError):
        normalize_ohlcv(raw, source="yfinance", symbol="AAPL")
