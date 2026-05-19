"""Broker adapter stubs for future paper-only integrations."""

from aurora.brokers.alpaca_paper import AlpacaPaperBrokerAdapter
from aurora.brokers.base import (
    BROKER_STUB_SAFETY_FLAGS,
    BrokerAdapter,
    BrokerAdapterConfig,
    BrokerAdapterError,
    BrokerOrderRequest,
    BrokerOrderResult,
    assert_no_live_trading,
)

__all__ = [
    "BROKER_STUB_SAFETY_FLAGS",
    "AlpacaPaperBrokerAdapter",
    "BrokerAdapter",
    "BrokerAdapterConfig",
    "BrokerAdapterError",
    "BrokerOrderRequest",
    "BrokerOrderResult",
    "assert_no_live_trading",
]
