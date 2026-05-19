import pytest

from aurora.data.base import MarketDataRequest
from aurora.data.exceptions import DataSourceError
from aurora.data.lseg_source import LSEGDataSource, LSEGDataSourceConfig
from aurora.data.source_resolver import get_data_source
from aurora.data.yfinance_source import YFinanceDataSource


def test_get_data_source_yfinance_returns_yfinance_instance():
    source = get_data_source("yfinance")
    assert isinstance(source, YFinanceDataSource)
    assert source.source_name == "yfinance"


def test_get_data_source_lseg_returns_lseg_instance():
    config = LSEGDataSourceConfig(enabled=True, app_key="key", username="user", password="pass")
    source = get_data_source("lseg", config=config)
    assert isinstance(source, LSEGDataSource)
    assert source.source_name == "lseg"
    assert source.config == config


def test_get_data_source_unknown_source_raises_value_error():
    with pytest.raises(ValueError, match="Unknown data source"):
        get_data_source("unknown_source")


def test_get_data_source_lseg_without_config_fails_closed():
    source = get_data_source("lseg")  # No config, no client
    health = source.health_check()
    assert health.ok is False
    assert "missing config" in health.message

    # get_bars should also fail closed
    with pytest.raises(DataSourceError, match="missing required config"):
        source.get_bars(MarketDataRequest(symbols=["SPY"], start="2024-01-01"))


def test_get_data_source_lseg_with_config_but_no_client_fails_closed():
    config = LSEGDataSourceConfig(enabled=True, app_key="key", username="user", password="pass")
    source = get_data_source("lseg", config=config)  # No client
    health = source.health_check()
    assert health.ok is False
    assert "client" in health.message

    with pytest.raises(DataSourceError, match="missing required config"):
        source.get_bars(MarketDataRequest(symbols=["SPY"], start="2024-01-01"))