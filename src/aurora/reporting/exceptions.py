"""Custom exceptions for reporting workflows."""


class AuroraReportingError(Exception):
    """Base exception for AURORA reporting errors."""


class ReportLoadError(AuroraReportingError):
    """Raised when a report cannot be loaded."""


class ReportSaveError(AuroraReportingError):
    """Raised when a report cannot be saved."""
