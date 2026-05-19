"""Custom exceptions for strategy workflows."""


class AuroraStrategyError(Exception):
    """Base exception for AURORA strategy layer errors."""


class StrategyConfigError(AuroraStrategyError):
    """Raised when a strategy configuration is invalid."""


class StrategyRegistryError(AuroraStrategyError):
    """Raised when strategy registry operations fail."""


class SignalGenerationError(AuroraStrategyError):
    """Raised when a strategy cannot generate signals."""
