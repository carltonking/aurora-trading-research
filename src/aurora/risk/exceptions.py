"""Custom exceptions for risk workflows."""


class AuroraRiskError(Exception):
    """Base exception for AURORA risk layer errors."""


class RiskConfigError(AuroraRiskError):
    """Raised when risk configuration is invalid."""


class RiskEvaluationError(AuroraRiskError):
    """Raised when a trade candidate cannot be evaluated."""
