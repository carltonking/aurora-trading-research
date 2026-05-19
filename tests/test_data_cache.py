import pandas as pd

from aurora.data.cache import cache_key, load_market_data, save_market_data


def test_cache_key_is_deterministic() -> None:
    first = cache_key("yfinance", ["MSFT", "AAPL"], "2020-01-01", None, "1d")
    second = cache_key("yfinance", ["AAPL", "MSFT"], "2020-01-01", None, "1d")

    assert first == second
    assert first == "yfinance_aapl-msft_2020-01-01_none_1d"


def test_save_load_round_trip_works(tmp_path) -> None:
    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2024-01-02"]),
            "symbol": ["AAPL"],
            "open": [100.0],
            "high": [102.0],
            "low": [99.0],
            "close": [101.0],
            "adjusted_close": [101.0],
            "volume": [1000],
            "source": ["test"],
            "asset_type": ["equity"],
            "currency": ["USD"],
        }
    )

    path = save_market_data(df, "test-key", base_dir=tmp_path)
    loaded = load_market_data("test-key", base_dir=tmp_path)

    assert path.exists()
    assert loaded is not None
    assert pd.api.types.is_datetime64_any_dtype(loaded["timestamp"])
    assert loaded.to_dict("records")[0]["symbol"] == "AAPL"


def test_missing_cache_returns_none(tmp_path) -> None:
    assert load_market_data("missing", base_dir=tmp_path) is None
