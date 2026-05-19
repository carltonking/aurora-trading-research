"""Data source factory/resolver for market data adapters."""

from aurora.data.base import MarketDataSource
from aurora.data.lseg_source import LSEGDataSource
from aurora.data.yfinance_source import YFinanceDataSource


def get_data_source(source_name: str, config=None, client=None) -> MarketDataSource:
    """Return a market data source instance by name.

    Args:
        source_name: Name of the data source ('yfinance' or 'lseg').
        config: Optional configuration for LSEGDataSource.
        client: Optional client for LSEGDataSource.

    Returns:
        MarketDataSource instance.

    Raises:
        ValueError: If source_name is not supported.
    """
    if source_name == "yfinance":
        return YFinanceDataSource()
    if source_name == "lseg":
        return LSEGDataSource(config=config, client=client)
    raise ValueError(f"Unknown data source: {source_name}. Supported: 'yfinance', 'lseg'")