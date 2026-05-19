"""Custom exceptions for validation workflows."""


class AuroraValidationError(Exception):
    """Base exception for AURORA validation errors."""


class WalkForwardValidationError(AuroraValidationError):
    """Raised when walk-forward validation cannot run."""


class OverfittingDiagnosticError(AuroraValidationError):
    """Raised when overfitting diagnostics cannot run."""
