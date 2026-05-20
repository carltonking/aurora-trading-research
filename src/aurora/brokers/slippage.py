"""Slippage models for paper trading."""

from abc import ABC, abstractmethod


class SlippageModel(ABC):
    """Abstract base class for slippage models."""

    @abstractmethod
    def apply(self, order_price: float, order_side: str, quantity: int) -> float:
        """Apply slippage to the order price.

        Args:
            order_price: The original order price.
            order_side: "buy" or "sell".
            quantity: Number of shares.

        Returns:
            The adjusted fill price after slippage.
        """
        pass


class NoSlippage(SlippageModel):
    """No slippage - returns original price."""

    def apply(self, order_price: float, order_side: str, quantity: int) -> float:
        return order_price


class FixedSlippage(SlippageModel):
    """Fixed cent slippage - adjusts price by fixed cents against trader."""

    def __init__(self, cents: float = 0.01) -> None:
        self.cents = cents

    def apply(self, order_price: float, order_side: str, quantity: int) -> float:
        if order_side.lower() == "buy":
            return order_price + self.cents
        else:
            return order_price - self.cents


class PercentageSlippage(SlippageModel):
    """Percentage slippage - adjusts price by percentage against trader."""

    def __init__(self, percent: float = 0.001) -> None:
        self.percent = percent

    def apply(self, order_price: float, order_side: str, quantity: int) -> float:
        adjustment = order_price * self.percent
        if order_side.lower() == "buy":
            return order_price + adjustment
        else:
            return order_price - adjustment