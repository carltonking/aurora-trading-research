"""Alpaca paper-only broker adapter.

This module provides a paper-trading-only interface to Alpaca's API.
Live trading is explicitly unsupported and will be blocked.

The adapter requires the optional alpaca-py package:
    pip install .[alpaca]

Configuration is loaded exclusively from environment variables:
- ALPACA_PAPER_KEY: Alpaca paper trading API key
- ALPACA_PAPER_SECRET: Alpaca paper trading secret key
- ALPACA_PAPER_ENABLED: Set to 'true' or '1' to enable (default: false)
"""

import os
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from aurora.brokers.commission import CommissionModel, NoCommission
from aurora.brokers.fill_simulator import FillModel, ImmediateFill
from aurora.brokers.latency import LatencyModel, NoLatency
from aurora.brokers.slippage import NoSlippage, SlippageModel


@runtime_checkable
class AlpacaPaperBrokerProtocol(Protocol):
    """Protocol for Alpaca paper broker clients.

    This protocol defines the interface for paper-only trading.
    Live trading methods are not included.
    """

    def health_check(self) -> dict[str, Any]:
        """Return health status of the Alpaca connection."""

    def get_account(self) -> dict[str, Any]:
        """Return paper account information."""

    def submit_paper_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        order_type: str = "market",
        price: float = 0.0,
    ) -> dict[str, Any]:
        """Submit a paper order.

        Args:
            symbol: Stock symbol (e.g., 'SPY').
            qty: Number of shares.
            side: 'buy' or 'sell'.
            order_type: Order type (default: 'market').
            price: Optional price for limit orders (default: 0 for market).

        Returns:
            Order status dict.
        """

    def cancel_paper_order(self, order_id: str) -> dict[str, Any]:
        """Cancel a paper order.

        Args:
            order_id: Order ID to cancel.

        Returns:
            Cancellation status dict.
        """

    def get_paper_positions(self) -> list[dict[str, Any]]:
        """Return current paper positions."""

    def get_paper_orders(self) -> list[dict[str, Any]]:
        """Return paper orders."""


@dataclass(frozen=True)
class AlpacaConfig:
    """Configuration for Alpaca paper broker."""

    enabled: bool = False
    api_key: str | None = None
    secret_key: str | None = None
    paper: bool = True

    def __repr__(self) -> str:
        return (
            f"AlpacaConfig("
            f"enabled={self.enabled}, "
            f"api_key={'***' if self.api_key else None}, "
            f"secret_key={'***' if self.secret_key else None}, "
            f"paper={self.paper})"
        )

    def __str__(self) -> str:
        return self.__repr__()


def load_alpaca_config_from_env() -> AlpacaConfig:
    """Load Alpaca configuration from environment variables only.

    Environment variables:
        ALPACA_PAPER_ENABLED: Set to 'true' or '1' to enable
        ALPACA_PAPER_KEY: Alpaca paper API key
        ALPACA_PAPER_SECRET: Alpaca paper secret key

    Returns:
        AlpacaConfig with values from environment or defaults.
    """
    enabled = os.getenv("ALPACA_PAPER_ENABLED", "").lower() in ("true", "1", "yes")
    api_key = os.getenv("ALPACA_PAPER_KEY") or None
    secret_key = os.getenv("ALPACA_PAPER_SECRET") or None

    return AlpacaConfig(
        enabled=enabled,
        api_key=api_key,
        secret_key=secret_key,
        paper=True,
    )


class AlpacaConnectionError(Exception):
    """Raised when connection to Alpaca API fails."""


class AlpacaLiveTradingError(Exception):
    """Raised when live trading is attempted."""


class RealAlpacaPaperClient:
    """Real Alpaca paper client requiring alpaca-py package.

    This client is paper-only. Live trading is explicitly blocked.

    Install with: pip install .[alpaca]
    """

    _SDK_IMPORT_ERROR = "Alpaca SDK not installed. Install with: pip install .[alpaca]"

    def __init__(self, config: AlpacaConfig) -> None:
        if not config.enabled:
            raise ValueError("Alpaca client is disabled. Set ALPACA_PAPER_ENABLED=true.")
        if not config.api_key:
            raise ValueError("Alpaca api_key is required.")
        if not config.secret_key:
            raise ValueError("Alpaca secret_key is required.")

        self._config = config
        self._sdk = self._import_sdk()

    def _import_sdk(self) -> Any:
        try:
            import alpaca
            return alpaca
        except ImportError as exc:
            raise ImportError(self._SDK_IMPORT_ERROR) from exc

    def __repr__(self) -> str:
        return (
            f"RealAlpacaPaperClient("
            f"enabled={self._config.enabled}, "
            f"api_key={'***' if self._config.api_key else None}, "
            f"secret_key={'***' if self._config.secret_key else None}, "
            f"paper={self._config.paper})"
        )

    def __str__(self) -> str:
        return self.__repr__()

    def _check_paper_account(self, account: dict) -> None:
        is_paper = account.get("paper", False) or account.get("account_type") == "paper"
        if not is_paper:
            raise AlpacaLiveTradingError(
                "Live trading is not supported. Only paper trading is allowed."
            )

    def health_check(self) -> dict[str, Any]:
        try:
            client = self._sdk.REST(
                self._config.api_key,
                self._config.secret_key,
                self._config.paper,
            )
            account = client.get_account()
            self._check_paper_account(account)
            return {
                "ok": True,
                "message": "Alpaca paper connection successful.",
                "details": {"source": "alpaca-py", "paper": True},
            }
        except ImportError as exc:
            return {"ok": False, "message": str(exc), "details": {}}
        except AlpacaLiveTradingError as exc:
            return {"ok": False, "message": str(exc), "details": {}}
        except Exception as exc:
            return {
                "ok": False,
                "message": f"Alpaca connection failed: {type(exc).__name__}",
                "details": {},
            }

    def get_account(self) -> dict[str, Any]:
        try:
            client = self._sdk.REST(
                self._config.api_key,
                self._config.secret_key,
                self._config.paper,
            )
            account = client.get_account()
            self._check_paper_account(account)
            return {
                "id": account.id,
                "status": account.status,
                "cash": account.cash,
                "portfolio_value": account.portfolio_value,
                "paper": True,
            }
        except ImportError as exc:
            raise AlpacaConnectionError(str(exc)) from exc
        except AlpacaLiveTradingError as exc:
            raise AlpacaConnectionError(str(exc)) from exc
        except Exception as exc:
            raise AlpacaConnectionError(
                f"Failed to get account: {type(exc).__name__}"
            ) from exc

    def submit_paper_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        order_type: str = "market",
    ) -> dict[str, Any]:
        try:
            client = self._sdk.REST(
                self._config.api_key,
                self._config.secret_key,
                self._config.paper,
            )
            order = client.submit_order(
                symbol=symbol,
                qty=qty,
                side=side,
                type=order_type,
                time_in_force="day",
            )
            return {
                "id": order.id,
                "symbol": order.symbol,
                "qty": order.qty,
                "side": order.side,
                "type": order.type,
                "status": order.status,
                "paper": True,
            }
        except ImportError as exc:
            raise AlpacaConnectionError(str(exc)) from exc
        except Exception as exc:
            raise AlpacaConnectionError(
                f"Failed to submit order: {type(exc).__name__}"
            ) from exc

    def cancel_paper_order(self, order_id: str) -> dict[str, Any]:
        try:
            client = self._sdk.REST(
                self._config.api_key,
                self._config.secret_key,
                self._config.paper,
            )
            client.cancel_order(order_id)
            return {
                "id": order_id,
                "status": "cancelled",
                "paper": True,
            }
        except ImportError as exc:
            raise AlpacaConnectionError(str(exc)) from exc
        except Exception as exc:
            raise AlpacaConnectionError(
                f"Failed to cancel order: {type(exc).__name__}"
            ) from exc

    def get_paper_positions(self) -> list[dict[str, Any]]:
        try:
            client = self._sdk.REST(
                self._config.api_key,
                self._config.secret_key,
                self._config.paper,
            )
            positions = client.get_positions()
            return [
                {
                    "symbol": p.symbol,
                    "qty": p.qty,
                    "market_value": p.market_value,
                    "cost_basis": p.cost_basis,
                    "paper": True,
                }
                for p in positions
            ]
        except ImportError as exc:
            raise AlpacaConnectionError(str(exc)) from exc
        except Exception as exc:
            raise AlpacaConnectionError(
                f"Failed to get positions: {type(exc).__name__}"
            ) from exc

    def get_paper_orders(self) -> list[dict[str, Any]]:
        try:
            client = self._sdk.REST(
                self._config.api_key,
                self._config.secret_key,
                self._config.paper,
            )
            orders = client.get_orders()
            return [
                {
                    "id": o.id,
                    "symbol": o.symbol,
                    "qty": o.qty,
                    "side": o.side,
                    "type": o.type,
                    "status": o.status,
                    "paper": True,
                }
                for o in orders
            ]
        except ImportError as exc:
            raise AlpacaConnectionError(str(exc)) from exc
        except Exception as exc:
            raise AlpacaConnectionError(
                f"Failed to get orders: {type(exc).__name__}"
            ) from exc


class FakeAlpacaPaperClient:
    """Fake Alpaca paper client for tests and dry-run.

    This client never makes network calls and returns canned responses.
    """

    def __init__(
        self,
        slippage_model: SlippageModel | None = None,
        commission_model: CommissionModel | None = None,
        latency_model: LatencyModel | None = None,
        fill_model: FillModel | None = None,
    ) -> None:
        self._slippage_model = slippage_model or NoSlippage()
        self._commission_model = commission_model or NoCommission()
        self._latency_model = latency_model or NoLatency()
        self._fill_model = fill_model or ImmediateFill()

    def health_check(self) -> dict[str, Any]:
        return {
            "ok": True,
            "message": "Fake Alpaca paper client (SDK not used)",
            "details": {"source": "fake", "paper": True},
        }

    def get_account(self) -> dict[str, Any]:
        return {
            "id": "fake-account-id",
            "status": "ACTIVE",
            "cash": "100000.00",
            "portfolio_value": "100000.00",
            "paper": True,
        }

    def submit_paper_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        order_type: str = "market",
        price: float = 0.0,
    ) -> dict[str, Any]:
        fill_price = price if price > 0 else 100.0
        adjusted_price = self._slippage_model.apply(fill_price, side, qty)

        latency_seconds = self._latency_model.delay({"symbol": symbol, "qty": qty, "side": side})

        order_dict = {
            "symbol": symbol,
            "qty": qty,
            "side": side,
            "price": adjusted_price,
            "order_type": order_type,
        }
        fill_result = self._fill_model.simulate_fill(order_dict)

        filled_qty = fill_result["filled_qty"]
        final_price = fill_result["average_price"]
        commission = self._commission_model.calculate(final_price * filled_qty, filled_qty)

        return {
            "id": f"fake-order-{symbol}-{qty}-{side}",
            "symbol": symbol,
            "qty": qty,
            "side": side,
            "type": order_type,
            "status": "accepted",
            "paper": True,
            "fill_price": final_price,
            "filled_qty": filled_qty,
            "fill_status": fill_result["status"],
            "fill_reason": fill_result.get("reason", ""),
            "slippage_applied": adjusted_price - fill_price,
            "commission_charged": commission,
            "latency_seconds": latency_seconds,
        }

    def cancel_paper_order(self, order_id: str) -> dict[str, Any]:
        return {
            "id": order_id,
            "status": "cancelled",
            "paper": True,
        }

    def get_paper_positions(self) -> list[dict[str, Any]]:
        return []

    def get_paper_orders(self) -> list[dict[str, Any]]:
        return []