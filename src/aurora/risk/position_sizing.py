"""Position sizing models for dynamic position sizing."""

from abc import ABC, abstractmethod
import math


class PositionSizer(ABC):
    """Abstract base class for position sizing models."""

    @abstractmethod
    def calculate(
        self,
        portfolio_value: float,
        price: float,
        strategy_edge: float = 0.01,
        volatility: float = 0.02,
        **kwargs,
    ) -> int:
        """Calculate the number of shares to trade.

        Args:
            portfolio_value: Total portfolio value in dollars.
            price: Current asset price.
            strategy_edge: Estimated strategy edge (default 0.01 = 1%).
            volatility: Asset volatility (default 0.02 = 2%).
            **kwargs: Additional parameters for specific sizers.

        Returns:
            Number of shares to trade (integer).
        """
        pass


class FixedFractionSizer(PositionSizer):
    """Fixed fraction of portfolio position sizing."""

    def __init__(self, fraction: float = 0.1) -> None:
        if not 0 < fraction <= 1:
            raise ValueError("fraction must be between 0 and 1")
        self.fraction = fraction

    def calculate(
        self,
        portfolio_value: float,
        price: float,
        strategy_edge: float = 0.01,
        volatility: float = 0.02,
        **kwargs,
    ) -> int:
        if portfolio_value <= 0 or price <= 0:
            return 0
        position_value = portfolio_value * self.fraction
        shares = position_value / price
        return int(math.floor(shares))


class KellySizer(PositionSizer):
    """Kelly criterion position sizing."""

    def __init__(
        self,
        multiplier: float = 0.5,
        win_rate: float = 0.5,
        avg_win: float = 1.0,
        avg_loss: float = 1.0,
    ) -> None:
        if not 0 < multiplier <= 1:
            raise ValueError("multiplier must be between 0 and 1")
        self.multiplier = multiplier
        self.win_rate = win_rate
        self.avg_win = avg_win
        self.avg_loss = avg_loss

    def calculate(
        self,
        portfolio_value: float,
        price: float,
        strategy_edge: float = 0.01,
        volatility: float = 0.02,
        **kwargs,
    ) -> int:
        if portfolio_value <= 0 or price <= 0:
            return 0

        win_prob = self.win_rate * strategy_edge
        loss_prob = (1 - self.win_rate) * 0.01

        if self.avg_loss == 0:
            kelly_fraction = win_prob
        else:
            win_loss_ratio = self.avg_win / self.avg_loss
            kelly_fraction = self.win_rate - (1 - self.win_rate) / win_loss_ratio

        kelly_fraction = max(0, kelly_fraction * self.multiplier)

        position_value = portfolio_value * kelly_fraction
        shares = position_value / price
        return int(math.floor(shares))


class VolatilityAdjustedSizer(PositionSizer):
    """Volatility-adjusted position sizing."""

    def __init__(
        self,
        target_volatility: float = 0.02,
        volatility_lookback: int = 20,
    ) -> None:
        if target_volatility <= 0:
            raise ValueError("target_volatility must be positive")
        self.target_volatility = target_volatility
        self.volatility_lookback = volatility_lookback

    def calculate(
        self,
        portfolio_value: float,
        price: float,
        strategy_edge: float = 0.01,
        volatility: float = 0.02,
        **kwargs,
    ) -> int:
        if portfolio_value <= 0 or price <= 0:
            return 0

        vol = volatility or 0.02
        if vol <= 0:
            vol = 0.02

        position_value = (self.target_volatility * portfolio_value) / vol
        shares = position_value / price
        return int(math.floor(shares))


class EqualRiskContributionSizer(PositionSizer):
    """Equal risk contribution position sizing."""

    def __init__(
        self,
        risk_per_trade: float = 0.01,
        stop_loss_pct: float = 0.02,
    ) -> None:
        if not 0 < risk_per_trade <= 1:
            raise ValueError("risk_per_trade must be between 0 and 1")
        if not 0 < stop_loss_pct <= 1:
            raise ValueError("stop_loss_pct must be between 0 and 1")
        self.risk_per_trade = risk_per_trade
        self.stop_loss_pct = stop_loss_pct

    def calculate(
        self,
        portfolio_value: float,
        price: float,
        strategy_edge: float = 0.01,
        volatility: float = 0.02,
        **kwargs,
    ) -> int:
        if portfolio_value <= 0 or price <= 0:
            return 0

        risk_amount = portfolio_value * self.risk_per_trade
        stop_value = price * self.stop_loss_pct

        if stop_value <= 0:
            return 0

        shares = risk_amount / stop_value
        return int(math.floor(shares))


def get_sizer_from_config(sizer_type: str, **kwargs) -> PositionSizer:
    """Get a position sizer from configuration string.

    Args:
        sizer_type: Type of sizer - "fixed_fraction", "kelly", "volatility", "equal_risk"
        **kwargs: Parameters for the sizer

    Returns:
        PositionSizer instance
    """
    if sizer_type == "fixed_fraction":
        return FixedFractionSizer(fraction=kwargs.get("fraction", 0.1))
    elif sizer_type == "kelly":
        return KellySizer(
            multiplier=kwargs.get("multiplier", 0.5),
            win_rate=kwargs.get("win_rate", 0.5),
            avg_win=kwargs.get("avg_win", 1.0),
            avg_loss=kwargs.get("avg_loss", 1.0),
        )
    elif sizer_type == "volatility":
        return VolatilityAdjustedSizer(
            target_volatility=kwargs.get("target_volatility", 0.02),
            volatility_lookback=kwargs.get("volatility_lookback", 20),
        )
    elif sizer_type == "equal_risk":
        return EqualRiskContributionSizer(
            risk_per_trade=kwargs.get("risk_per_trade", 0.01),
            stop_loss_pct=kwargs.get("stop_loss_pct", 0.02),
        )
    else:
        return FixedFractionSizer()