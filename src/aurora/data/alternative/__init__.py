"""Alternative data sources: FRED, SEC EDGAR, News API."""

from aurora.data.alternative.fred_source import FredConfig, FredSource
from aurora.data.alternative.sec_source import SecConfig, SecSource
from aurora.data.alternative.news_source import NewsConfig, NewsSource

__all__ = ["FredConfig", "FredSource", "SecConfig", "SecSource", "NewsConfig", "NewsSource"]