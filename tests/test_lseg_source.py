import os
import pandas as pd
import pytest

from aurora.data.base import MarketDataRequest
from aurora.data.exceptions import DataSourceError
from aurora.data.lseg_source import LSEGDataSource, LSEGDataSourceConfig, load_lseg_config_from_env
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


def test_load_lseg_config_from_env_returns_defaults_when_no_env(monkeypatch) -> None:
    monkeypatch.delenv("LSEG_ENABLED", raising=False)
    monkeypatch.delenv("LSEG_APP_KEY", raising=False)
    monkeypatch.delenv("LSEG_USERNAME", raising=False)
    monkeypatch.delenv("LSEG_PASSWORD", raising=False)

    config = load_lseg_config_from_env()

    assert config.enabled is False
    assert config.app_key is None
    assert config.username is None
    assert config.password is None


def test_load_lseg_config_from_env_reads_enabled_true(monkeypatch) -> None:
    monkeypatch.setenv("LSEG_ENABLED", "true")
    monkeypatch.setenv("LSEG_APP_KEY", "test-key")
    monkeypatch.setenv("LSEG_USERNAME", "test-user")
    monkeypatch.setenv("LSEG_PASSWORD", "test-pass")

    config = load_lseg_config_from_env()

    assert config.enabled is True
    assert config.app_key == "test-key"
    assert config.username == "test-user"
    assert config.password == "test-pass"


def test_load_lseg_config_from_env_accepts_various_true_values(monkeypatch) -> None:
    for value in ("1", "yes", "True", "TRUE"):
        monkeypatch.setenv("LSEG_ENABLED", value)
        config = load_lseg_config_from_env()
        assert config.enabled is True


def test_load_lseg_config_from_env_missing_credentials_disables(monkeypatch) -> None:
    monkeypatch.setenv("LSEG_ENABLED", "true")
    monkeypatch.delenv("LSEG_APP_KEY", raising=False)
    monkeypatch.delenv("LSEG_USERNAME", raising=False)
    monkeypatch.delenv("LSEG_PASSWORD", raising=False)

    config = load_lseg_config_from_env()

    assert config.enabled is True
    assert config.app_key is None
    assert config.username is None
    assert config.password is None


def test_config_repr_does_not_expose_secrets() -> None:
    config = LSEGDataSourceConfig(
        enabled=True,
        app_key="secret-app-key",
        username="secret-user",
        password="secret-password",
    )

    repr_str = repr(config)

    assert "secret-app-key" not in repr_str
    assert "secret-user" not in repr_str
    assert "secret-password" not in repr_str
    assert "***" in repr_str


def test_config_str_does_not_expose_secrets() -> None:
    config = LSEGDataSourceConfig(
        enabled=True,
        app_key="secret-app-key",
        username="secret-user",
        password="secret-password",
    )

    str_str = str(config)

    assert "secret-app-key" not in str_str
    assert "secret-user" not in str_str
    assert "secret-password" not in str_str
    assert "***" in str_str


def test_health_check_message_does_not_expose_secrets() -> None:
    config = LSEGDataSourceConfig(
        enabled=True,
        app_key="secret-app-key",
        username="secret-user",
        password="secret-password",
    )
    source = LSEGDataSource(config=config, client=FakeLSEGClient(_raw_rows()))

    health = source.health_check()

    assert "secret-app-key" not in health.message
    assert "secret-user" not in health.message
    assert "secret-password" not in health.message


def test_get_bars_error_message_does_not_expose_secrets() -> None:
    config = LSEGDataSourceConfig(
        enabled=True,
        app_key="secret-app-key",
        username="secret-user",
        password="secret-password",
    )
    source = LSEGDataSource(config=config)

    with pytest.raises(DataSourceError) as exc_info:
        source.get_bars(MarketDataRequest(symbols=["SPY"], start="2024-01-01"))

    error_message = str(exc_info.value)
    assert "secret-app-key" not in error_message
    assert "secret-user" not in error_message
    assert "secret-password" not in error_message


def test_fails_closed_without_injected_client(monkeypatch) -> None:
    monkeypatch.setenv("LSEG_ENABLED", "true")
    monkeypatch.setenv("LSEG_APP_KEY", "test-key")
    monkeypatch.setenv("LSEG_USERNAME", "test-user")
    monkeypatch.setenv("LSEG_PASSWORD", "test-pass")

    config = load_lseg_config_from_env()
    source = LSEGDataSource(config=config, client=None)

    health = source.health_check()

    assert health.ok is False
    assert "client" in health.message

    with pytest.raises(DataSourceError, match="missing required config"):
        source.get_bars(MarketDataRequest(symbols=["SPY"], start="2024-01-01"))


def test_config_only_loads_from_env_not_hardcoded(monkeypatch) -> None:
    monkeypatch.setenv("LSEG_ENABLED", "true")
    monkeypatch.setenv("LSEG_APP_KEY", "env-key")
    monkeypatch.setenv("LSEG_USERNAME", "env-user")
    monkeypatch.setenv("LSEG_PASSWORD", "env-pass")

    config = load_lseg_config_from_env()

    assert config.app_key == "env-key"
    assert config.username == "env-user"
    assert config.password == "env-pass"

    monkeypatch.setenv("LSEG_APP_KEY", "new-key")
    config2 = load_lseg_config_from_env()
    assert config2.app_key == "new-key"
