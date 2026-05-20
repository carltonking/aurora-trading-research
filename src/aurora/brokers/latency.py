"""Latency models for paper trading simulation."""

from abc import ABC, abstractmethod
import random


class LatencyModel(ABC):
    """Abstract base class for latency models."""

    @abstractmethod
    def delay(self, order: dict) -> float:
        """Calculate simulated delay for an order.

        Args:
            order: Order dict with keys like symbol, qty, side, etc.

        Returns:
            Delay in seconds.
        """
        pass


class NoLatency(LatencyModel):
    """No latency - returns zero delay."""

    def delay(self, order: dict) -> float:
        return 0.0


class FixedLatency(LatencyModel):
    """Fixed latency delay."""

    def __init__(self, seconds: float = 1.0) -> None:
        self.seconds = seconds

    def delay(self, order: dict) -> float:
        return self.seconds


class RandomLatency(LatencyModel):
    """Random latency between min and max seconds."""

    def __init__(self, min_seconds: float = 0.5, max_seconds: float = 2.0) -> None:
        self.min_seconds = min_seconds
        self.max_seconds = max_seconds

    def delay(self, order: dict) -> float:
        return random.uniform(self.min_seconds, self.max_seconds)