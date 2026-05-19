import pandas as pd
import pytest

from aurora.data.base import MarketDataRequest
from aurora.data.exceptions import DataSourceError
from aurora.data.lseg_source import LSEGDataSource, LSEGDataSourceConfig
from aurora.data.normalize import STANDARD_OHLCV_COLUMNS


def test_health_check_when_disabled_or_missing_config_is_unhealthy() -> None:
    source = LSEGDataSource()

    health = source.health_check()

    assert health.source_name == "lseg"
    assert health.ok is False
    assert "missing config" in health.message
    assert "enabled" in health.message
    assert "client" in health.message


def test_health_check_with_injected_fake_client_is_healthy() -> None:
    source = LSEGDataSource(config=_config(), client=FakeLSEGClient(_raw_rows()))

    health = source.health_check()

    assert health.ok is True
    assert "injected client" in health.message


def test_get_bars_missing_config_raises_data_source_error() -> None:
    source = LSEGDataSource(client=FakeLSEGClient(_raw_rows()))

    with pytest.raises(DataSourceError, match="missing required config"):
        source.get_bars(MarketDataRequest(symbols=["SPY"], start="2024-01-01"))


def test_get_bars_successful_mocked_response_returns_normalized_rows() -> None:
    source = LSEGDataSource(config=_config(), client=FakeLSEGClient(_raw_rows()))

    result = source.get_bars(
        MarketDataRequest(symbols=["SPY", "QQQ"], start="2024-01-01", end="2024-01-03")
    )

    assert list(result.columns) == STANDARD_OHLCV_COLUMNS
    assert result["symbol"].tolist() == ["QQQ", "SPY"]
    assert result["source"].unique().tolist() == ["lseg"]
    assert result["asset_type"].unique().tolist() == ["equity"]
    assert result["currency"].unique().tolist() == ["USD"]
    assert pd.api.types.is_datetime64_any_dtype(result["timestamp"])


def test_get_bars_successful_symbol_dict_response_returns_normalized_rows() -> None:
    source = LSEGDataSource(
        config=_config(),
        client=FakeLSEGClient(
            {
                "SPY": pd.DataFrame(
                    {
                        "Date": ["2024-01-02"],
                        "Open": [100.0],
                        "High": [102.0],
                        "Low": [99.0],
                        "Close": [101.0],
                        "Volume": [1000],
                    }
                )
            }
        ),
    )

    result = source.get_bars(MarketDataRequest(symbols=["SPY"], start="2024-01-01"))

    assert len(result) == 1
    assert result.loc[0, "symbol"] == "SPY"
    assert result.loc[0, "adjusted_close"] == 101.0


def test_empty_response_raises_data_source_error() -> None:
    source = LSEGDataSource(config=_config(), client=FakeLSEGClient([]))

    with pytest.raises(DataSourceError, match="no data"):
        source.get_bars(MarketDataRequest(symbols=["SPY"], start="2024-01-01"))


class FakeLSEGClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get_ohlcv(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def _config() -> LSEGDataSourceConfig:
    return LSEGDataSourceConfig(
        enabled=True,
        app_key="test-app-key",
        username="test-user",
        password="test-password",
    )


def _raw_rows() -> list[dict]:
    return [
        {
            "timestamp": "2024-01-02",
            "symbol": "SPY",
            "open": 100.0,
            "high": 102.0,
            "low": 99.0,
            "close": 101.0,
            "adjusted_close": 100.5,
            "volume": 1000,
        },
        {
            "timestamp": "2024-01-02",
            "symbol": "QQQ",
            "open": 200.0,
            "high": 202.0,
            "low": 199.0,
            "close": 201.0,
            "adjusted_close": 200.5,
            "volume": 2000,
        },
    ]
