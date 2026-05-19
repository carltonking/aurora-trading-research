"""Custom exceptions for market data workflows."""


class AuroraDataError(Exception):
    """Base exception for AURORA data layer errors."""


class DataSourceError(AuroraDataError):
    """Raised when a market data source cannot return usable data."""


class DataNormalizationError(AuroraDataError):
    """Raised when raw market data cannot be normalized."""


class DataQualityError(AuroraDataError):
    """Raised when market data fails required quality checks."""
