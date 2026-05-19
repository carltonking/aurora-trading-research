"""Market data interfaces and utilities."""

from aurora.data.base import DataSourceHealth, MarketDataRequest, MarketDataSource
from aurora.data.lseg_source import LSEGDataSource, LSEGDataSourceConfig
from aurora.data.normalize import normalize_ohlcv
from aurora.data.quality import DataQualityIssue, DataQualityReport, validate_ohlcv_quality
from aurora.data.source_resolver import get_data_source
from aurora.data.yfinance_source import YFinanceDataSource

__all__ = [
    "DataQualityIssue",
    "DataQualityReport",
    "DataSourceHealth",
    "LSEGDataSource",
    "LSEGDataSourceConfig",
    "MarketDataRequest",
    "MarketDataSource",
    "YFinanceDataSource",
    "get_data_source",
    "normalize_ohlcv",
    "validate_ohlcv_quality",
]
