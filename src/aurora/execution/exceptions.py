"""Custom exceptions for local execution simulation."""


class AuroraExecutionError(Exception):
    """Base exception for AURORA execution simulation errors."""


class BrokerExecutionError(AuroraExecutionError):
    """Raised when the simulation broker cannot process a candidate."""


class LedgerError(AuroraExecutionError):
    """Raised when the paper ledger cannot read or write state."""
