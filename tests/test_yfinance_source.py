import pandas as pd
import pytest

from aurora.data.base import MarketDataRequest
from aurora.data.exceptions import DataSourceError
from aurora.data.yfinance_source import YFinanceDataSource


def test_single_symbol_download(monkeypatch) -> None:
    raw = pd.DataFrame(
        {
            "Open": [100.0],
            "High": [102.0],
            "Low": [99.0],
            "Close": [101.0],
            "Adj Close": [100.5],
            "Volume": [1000],
        },
        index=pd.to_datetime(["2024-01-02"]),
    )

    def fake_download(**kwargs):
        assert kwargs["tickers"] == "AAPL"
        assert kwargs["start"] == "2024-01-01"
        return raw

    monkeypatch.setattr("aurora.data.yfinance_source.yf.download", fake_download)

    source = YFinanceDataSource()
    result = source.get_bars(MarketDataRequest(symbols=["AAPL"], start="2024-01-01"))

    assert len(result) == 1
    assert result.loc[0, "symbol"] == "AAPL"
    assert result.loc[0, "source"] == "yfinance"


def test_empty_download_raises(monkeypatch) -> None:
    def fake_download(**kwargs):
        return pd.DataFrame()

    monkeypatch.setattr("aurora.data.yfinance_source.yf.download", fake_download)

    source = YFinanceDataSource()
    with pytest.raises(DataSourceError):
        source.get_bars(MarketDataRequest(symbols=["AAPL"], start="2024-01-01"))
