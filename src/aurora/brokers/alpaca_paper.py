"""Disabled Alpaca paper adapter stub.

This module intentionally contains no broker SDK imports, network clients, endpoint
configuration, or credential fields.
"""

from typing import Any

from aurora.brokers.base import (
    BrokerAdapter,
    BrokerAdapterConfig,
    BrokerAdapterError,
    BrokerOrderRequest,
    BrokerOrderResult,
    assert_no_live_trading,
)


class AlpacaPaperBrokerAdapter(BrokerAdapter):
    """Non-network paper adapter stub for a future controlled implementation."""

    name = "alpaca_paper_stub"

    def __init__(self, config: BrokerAdapterConfig | None = None) -> None:
        super().__init__(config=config)

    def validate_config(self) -> None:
        """Validate that the stub remains paper-only and dry-run-only."""
        assert_no_live_trading(self.config)
        if not self.config.dry_run:
            raise BrokerAdapterError(
                "Alpaca paper adapter stub requires dry_run=True because broker submission "
                "is not implemented."
            )
        if self.config.enabled and not self.config.dry_run:
            raise BrokerAdapterError(
                "Alpaca paper adapter stub cannot be enabled for non-dry-run submission."
            )

    def submit_order(
        self,
        request: BrokerOrderRequest,
        risk_approved: bool = False,
    ) -> BrokerOrderResult:
        """Return a rejected dry-run result without contacting any broker."""
        self.validate_config()
        if self.config.require_risk_approval and not risk_approved:
            return BrokerOrderResult(
                accepted=False,
                broker_order_id=None,
                status="REJECTED",
                message="RiskManager approval is required before broker adapter submission.",
                raw_response={"adapter": self.name, "dry_run": True},
            )
        return BrokerOrderResult(
            accepted=False,
            broker_order_id=None,
            status="DRY_RUN_REJECTED",
            message=(
                "Alpaca paper adapter is a non-network stub; no broker order was submitted."
            ),
            raw_response={
                "adapter": self.name,
                "dry_run": True,
                "enabled": self.config.enabled,
                "symbol": request.symbol,
                "side": request.side,
                "quantity": request.quantity,
            },
        )

    def get_account(self) -> dict[str, Any]:
        """Return an empty dry-run account structure."""
        self.validate_config()
        return {"adapter": self.name, "dry_run": True, "account": None}

    def get_positions(self) -> list[dict[str, Any]]:
        """Return an empty dry-run position list."""
        self.validate_config()
        return []
