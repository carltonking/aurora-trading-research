"""Commission models for paper trading."""

from abc import ABC, abstractmethod


class CommissionModel(ABC):
    """Abstract base class for commission models."""

    @abstractmethod
    def calculate(self, order_value: float, quantity: int) -> float:
        """Calculate commission for an order.

        Args:
            order_value: Total value of the order (price * quantity).
            quantity: Number of shares.

        Returns:
            Commission cost in dollars.
        """
        pass


class NoCommission(CommissionModel):
    """No commission - returns zero."""

    def calculate(self, order_value: float, quantity: int) -> float:
        return 0.0


class FixedCommission(CommissionModel):
    """Fixed fee per trade."""

    def __init__(self, per_trade: float = 0.0) -> None:
        self.per_trade = per_trade

    def calculate(self, order_value: float, quantity: int) -> float:
        return self.per_trade


class PerShareCommission(CommissionModel):
    """Per-share commission."""

    def __init__(self, per_share: float = 0.005) -> None:
        self.per_share = per_share

    def calculate(self, order_value: float, quantity: int) -> float:
        return self.per_share * quantity