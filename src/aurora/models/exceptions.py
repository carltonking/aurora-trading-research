"""Custom exceptions for model workflows."""


class AuroraModelError(Exception):
    """Base exception for AURORA model layer errors."""


class LabelGenerationError(AuroraModelError):
    """Raised when supervised labels cannot be generated."""


class ModelTrainingError(AuroraModelError):
    """Raised when a model cannot be trained safely."""


class ModelRegistryError(AuroraModelError):
    """Raised when model registry operations fail."""
