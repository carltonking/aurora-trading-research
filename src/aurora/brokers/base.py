"""Fail-closed broker adapter interfaces for future paper integrations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


class BrokerAdapterError(Exception):
    """Raised when a broker adapter request is unsafe or unsupported."""


@dataclass(frozen=True)
class BrokerOrderRequest:
    """Structured request for a future paper broker adapter."""

    symbol: str
    side: str
    quantity: float
    order_type: str = "market"
    time_in_force: str = "day"
    client_order_id: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class BrokerOrderResult:
    """Structured result from a broker adapter attempt."""

    accepted: bool
    broker_order_id: str | None
    status: str
    message: str
    raw_response: dict[str, Any] | None = None


@dataclass(frozen=True)
class BrokerAdapterConfig:
    """Safety configuration for broker adapter stubs."""

    enabled: bool = False
    paper_only: bool = True
    allow_live_trading: bool = False
    dry_run: bool = True
    require_risk_approval: bool = True


BROKER_STUB_SAFETY_FLAGS = {
    "paper_broker_stub_only": True,
    "live_trading": False,
    "real_broker_used": False,
    "placed_real_orders": False,
    "external_llm_calls": False,
}


def assert_no_live_trading(config: BrokerAdapterConfig) -> None:
    """Reject broker configurations that cross AURORA's paper-only boundary."""
    if not config.paper_only:
        raise BrokerAdapterError("Broker adapters must remain paper_only.")
    if config.allow_live_trading:
        raise BrokerAdapterError("Broker adapters must keep allow_live_trading disabled.")


class BrokerAdapter(ABC):
    """Fail-closed interface for future paper broker adapters."""

    name = "base"

    def __init__(self, config: BrokerAdapterConfig | None = None) -> None:
        self.config = config or BrokerAdapterConfig()

    def validate_config(self) -> None:
        """Validate base safety constraints."""
        assert_no_live_trading(self.config)
        if not self.config.dry_run:
            raise BrokerAdapterError("Base broker adapter only supports dry_run mode.")

    def submit_order(
        self,
        request: BrokerOrderRequest,
        risk_approved: bool = False,
    ) -> BrokerOrderResult:
        """Reject all order requests in the base adapter."""
        self.validate_config()
        if self.config.require_risk_approval and not risk_approved:
            return BrokerOrderResult(
                accepted=False,
                broker_order_id=None,
                status="REJECTED",
                message="RiskManager approval is required before broker adapter submission.",
            )
        return BrokerOrderResult(
            accepted=False,
            broker_order_id=None,
            status="DRY_RUN_REJECTED",
            message="Base broker adapter is a non-executing stub and did not submit an order.",
            raw_response={"adapter": self.name, "request_symbol": request.symbol},
        )

    @abstractmethod
    def get_account(self) -> dict[str, Any]:
        """Return broker account data, if implemented."""

    @abstractmethod
    def get_positions(self) -> list[dict[str, Any]]:
        """Return broker position data, if implemented."""
