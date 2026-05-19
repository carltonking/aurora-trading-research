import pandas as pd

from aurora.data.quality import validate_ohlcv_quality


def _valid_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]),
            "symbol": ["AAPL", "AAPL", "AAPL"],
            "open": [100.0, 101.0, 102.0],
            "high": [102.0, 103.0, 104.0],
            "low": [99.0, 100.0, 101.0],
            "close": [101.0, 102.0, 103.0],
            "adjusted_close": [101.0, 102.0, 103.0],
            "volume": [1000, 1100, 1200],
            "source": ["test", "test", "test"],
            "asset_type": ["equity", "equity", "equity"],
            "currency": ["USD", "USD", "USD"],
        }
    )


def test_valid_dataframe_returns_ok_true() -> None:
    report = validate_ohlcv_quality(_valid_df())

    assert report.ok is True
    assert report.row_count == 3
    assert report.symbol_count == 1
    assert report.issues == []


def test_duplicate_rows_produce_error() -> None:
    df = pd.concat([_valid_df(), _valid_df().iloc[[0]]], ignore_index=True)

    report = validate_ohlcv_quality(df)

    assert report.ok is False
    assert any(issue.code == "duplicate_symbol_timestamp" for issue in report.issues)


def test_negative_price_produces_error() -> None:
    df = _valid_df()
    df.loc[1, "close"] = -1.0

    report = validate_ohlcv_quality(df)

    assert report.ok is False
    assert any(issue.code == "non_positive_price" for issue in report.issues)


def test_large_move_produces_warning_but_ok_remains_true() -> None:
    df = _valid_df()
    df.loc[1, "close"] = 200.0

    report = validate_ohlcv_quality(df)

    assert report.ok is True
    assert any(issue.code == "large_close_to_close_move" for issue in report.issues)
    assert all(issue.severity == "warning" for issue in report.issues)
