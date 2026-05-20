"""Plugin base classes for AURORA extension system.

This module defines abstract base classes that plugins must implement
to extend AURORA's data sources, broker adapters, and optimizers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

import pandas as pd


class DataSourcePlugin(ABC):
    """Abstract base class for data source plugins."""

    @abstractmethod
    def fetch_data(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        interval: str = "1d",
    ) -> pd.DataFrame:
        """Fetch market data for a symbol.

        Args:
            symbol: Stock/instrument symbol.
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).
            interval: Data interval (e.g., "1d", "1h", "5m").

        Returns:
            DataFrame with columns: date, open, high, low, close, volume.

        Raises:
            ValueError: If fetch fails.
        """
        pass

    @abstractmethod
    def health_check(self) -> dict[str, Any]:
        """Check data source health.

        Returns:
            Health status dictionary with 'status' and optional 'reason'.
        """
        pass


class BrokerPlugin(ABC):
    """Abstract base class for broker adapters (paper-only)."""

    @abstractmethod
    def health_check(self) -> dict[str, Any]:
        """Check broker connection health.

        Returns:
            Health status dictionary.
        """
        pass

    @abstractmethod
    def get_account(self) -> dict[str, Any]:
        """Get account information.

        Returns:
            Account dictionary with equity, cash, positions value.
        """
        pass

    @abstractmethod
    def submit_order(
        self,
        symbol: str,
        quantity: float,
        side: str,
        order_type: str = "market",
        limit_price: Optional[float] = None,
    ) -> dict[str, Any]:
        """Submit an order.

        Args:
            symbol: Stock symbol.
            quantity: Number of shares.
            side: "buy" or "sell".
            order_type: "market", "limit", etc.
            limit_price: Limit price for limit orders.

        Returns:
            Order dictionary with status.

        Raises:
            ValueError: If order is rejected.
            RuntimeError: If live trading attempted.
        """
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> dict[str, Any]:
        """Cancel an order.

        Args:
            order_id: Order ID to cancel.

        Returns:
            Cancellation result.
        """
        pass

    @abstractmethod
    def get_positions(self) -> list[dict[str, Any]]:
        """Get current positions.

        Returns:
            List of position dictionaries.
        """
        pass

    @abstractmethod
    def get_orders(self, status: Optional[str] = None) -> list[dict[str, Any]]:
        """Get orders.

        Args:
            status: Filter by status (open, filled, cancelled, etc.).

        Returns:
            List of order dictionaries.
        """
        pass


class OptimizerPlugin(ABC):
    """Abstract base class for strategy optimizers."""

    @abstractmethod
    def optimize(
        self,
        strategy_builder: Any,
        data: pd.DataFrame,
        param_space: dict[str, Any],
        metric: str = "sharpe",
        max_iterations: int = 50,
    ) -> dict[str, Any]:
        """Run optimization.

        Args:
            strategy_builder: Strategy builder instance.
            data: Market data DataFrame.
            param_space: Parameter space to search.
            metric: Optimization metric (sharpe, returns, etc.).
            max_iterations: Maximum optimization iterations.

        Returns:
            Dictionary with best parameters and score.
        """
        pass

    @abstractmethod
    def health_check(self) -> dict[str, Any]:
        """Check optimizer health.

        Returns:
            Health status dictionary.
        """
        pass