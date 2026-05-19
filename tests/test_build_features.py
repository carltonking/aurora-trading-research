import pandas as pd

from aurora.data.normalize import STANDARD_OHLCV_COLUMNS
from aurora.features.build_features import build_features, get_feature_columns


def _sample_ohlcv(symbols: list[str] | None = None, periods: int = 60) -> pd.DataFrame:
    symbols = symbols or ["AAPL"]
    rows = []
    for symbol_index, symbol in enumerate(symbols):
        for i in range(periods):
            close = 100.0 + symbol_index * 100 + i
            rows.append(
                {
                    "timestamp": pd.Timestamp("2024-01-01") + pd.Timedelta(days=i),
                    "symbol": symbol,
                    "open": close - 0.5,
                    "high": close + 1.0,
                    "low": close - 1.0,
                    "close": close,
                    "adjusted_close": close,
                    "volume": 1000 + i,
                    "source": "test",
                    "asset_type": "equity",
                    "currency": "USD",
                }
            )
    return pd.DataFrame(rows)


def test_build_features_preserves_original_columns() -> None:
    df = _sample_ohlcv()

    result = build_features(df)

    for column in STANDARD_OHLCV_COLUMNS:
        assert column in result.columns


def test_build_features_adds_expected_feature_columns() -> None:
    df = _sample_ohlcv()

    result = build_features(df)

    expected = {
        "return_1d",
        "return_5d",
        "return_20d",
        "log_return_1d",
        "ma_10",
        "ma_20",
        "ma_50",
        "ma_200",
        "volatility_10",
        "volatility_20",
        "rsi_14",
        "macd",
        "macd_signal",
        "macd_hist",
        "atr_14",
        "drawdown",
        "dist_ma_20",
        "dist_ma_50",
        "rolling_high_20",
        "rolling_low_20",
        "volume_change_1d",
        "volume_change_5d",
    }
    assert expected.issubset(set(result.columns))


def test_build_features_works_for_multiple_symbols_independently() -> None:
    df = _sample_ohlcv(["AAPL", "MSFT"], periods=5)

    result = build_features(
        df,
        config={
            "moving_averages": [2],
            "volatility_windows": [2],
            "rsi_windows": [2],
            "macd": {"enabled": False},
            "atr_windows": [2],
            "distance_ma_windows": [2],
            "rolling_high_low_windows": [2],
            "volume_change_periods": [1],
        },
    )

    first_rows = result.groupby("symbol", sort=False).head(1)
    assert first_rows["return_1d"].isna().all()


def test_get_feature_columns_excludes_ohlcv_columns() -> None:
    result = build_features(_sample_ohlcv())

    feature_columns = get_feature_columns(result)

    assert "timestamp" not in feature_columns
    assert "symbol" not in feature_columns
    assert "return_1d" in feature_columns


def test_dropna_true_reduces_or_equal_row_count() -> None:
    df = _sample_ohlcv(periods=250)

    keepna = build_features(df, dropna=False)
    dropna = build_features(df, dropna=True)

    assert len(dropna) <= len(keepna)
    assert len(dropna) > 0
