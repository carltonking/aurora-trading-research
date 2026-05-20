"""Fill simulation models for paper trading."""

from abc import ABC, abstractmethod
import random
from typing import Any


class FillModel(ABC):
    """Abstract base class for fill models."""

    @abstractmethod
    def simulate_fill(self, order: dict) -> dict:
        """Simulate fill result for an order.

        Args:
            order: Order dict with keys: symbol, qty, side, price, etc.

        Returns:
            Fill result dict with: filled_qty, average_price, status, reason
        """
        pass


class ImmediateFill(FillModel):
    """Immediate full fill - backward compatible."""

    def simulate_fill(self, order: dict) -> dict:
        return {
            "filled_qty": order.get("qty", 0),
            "average_price": order.get("price", 0.0),
            "status": "filled",
            "reason": "immediate_fill",
        }


class PartialFill(FillModel):
    """Partial fill with configurable probability."""

    def __init__(
        self,
        fill_probability: float = 0.95,
        partial_pct_mean: float = 0.8,
    ) -> None:
        self.fill_probability = fill_probability
        self.partial_pct_mean = partial_pct_mean

    def simulate_fill(self, order: dict) -> dict:
        qty = order.get("qty", 0)
        price = order.get("price", 0.0)

        if random.random() > self.fill_probability:
            return {
                "filled_qty": 0,
                "average_price": price,
                "status": "no_fill",
                "reason": "fill_rejected",
            }

        pct = random.betavariate(5, 2) * self.partial_pct_mean + 0.1
        pct = min(max(pct, 0.0), 1.0)
        filled_qty = int(qty * pct)

        if filled_qty == 0:
            return {
                "filled_qty": 0,
                "average_price": price,
                "status": "no_fill",
                "reason": "partial_rejected",
            }

        return {
            "filled_qty": filled_qty,
            "average_price": price,
            "status": "partial" if filled_qty < qty else "filled",
            "reason": f"partial_fill_{filled_qty}/{qty}",
        }


class QueueDelayFill(FillModel):
    """Wraps a fill model with latency simulation."""

    def __init__(self, base_fill_model: FillModel, latency_model: Any) -> None:
        self.base_fill_model = base_fill_model
        self.latency_model = latency_model

    def simulate_fill(self, order: dict) -> dict:
        delay = self.latency_model.delay(order)
        result = self.base_fill_model.simulate_fill(order)
        result["latency_seconds"] = delay
        return result