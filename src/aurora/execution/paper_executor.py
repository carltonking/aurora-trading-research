"""Paper execution path with RiskManager gating.

This module provides a paper executor that sits between strategy signals
and the Alpaca paper broker adapter. Every execution candidate must pass
RiskManager before any broker call.
"""

import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

from aurora.brokers.alpaca_adapter import AlpacaPaperBrokerProtocol
from aurora.data.streaming.base import MarketDataStream
from aurora.execution.ledger import PaperLedger
from aurora.risk.models import (
    RISK_APPROVED,
    RISK_KILL_SWITCH_TRIGGERED,
    RISK_REDUCED_SIZE,
    RISK_REJECTED,
    PortfolioState,
    RiskDecision,
    TradeCandidate,
)
from aurora.risk.risk_manager import RiskManager


@dataclass
class PaperExecutionRequest:
    """Execution request for paper trading."""

    candidate_id: str
    strategy_name: str
    symbol: str
    quantity: int
    side: str
    order_type: str = "market"
    price: float = 0.0
    signal_metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class PaperExecutionResult:
    """Result of a paper execution attempt."""

    request: PaperExecutionRequest
    risk_decision: RiskDecision | None
    broker_response: dict[str, Any] | None
    reason: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "request": {
                "candidate_id": self.request.candidate_id,
                "strategy_name": self.request.strategy_name,
                "symbol": self.request.symbol,
                "quantity": self.request.quantity,
                "side": self.request.side,
                "order_type": self.request.order_type,
                "price": self.request.price,
                "timestamp": self.request.timestamp,
            },
            "risk_decision": {
                "status": self.risk_decision.status if self.risk_decision else None,
                "approved": self.risk_decision.approved if self.risk_decision else None,
                "final_quantity": self.risk_decision.final_quantity if self.risk_decision else 0,
                "reasons": self.risk_decision.reasons if self.risk_decision else [],
            }
            if self.risk_decision
            else None,
            "broker_response": self.broker_response,
            "reason": self.reason,
            "timestamp": self.timestamp,
        }


class PaperExecutor:
    """Paper executor that gates all orders through RiskManager.

    This executor ensures that every paper execution candidate passes
    RiskManager before any broker adapter call. Rejected and kill-switch
    candidates are never submitted to the broker.
    """

    def __init__(
        self,
        risk_manager: RiskManager,
        broker_client: AlpacaPaperBrokerProtocol,
        ledger: PaperLedger | None = None,
        portfolio: PortfolioState | None = None,
        stream: Optional[MarketDataStream] = None,
    ) -> None:
        self.risk_manager = risk_manager
        self.broker_client = broker_client
        self.ledger = ledger or PaperLedger()
        self.portfolio = portfolio or PortfolioState(
            equity=100000.0,
            cash=100000.0,
            market_value=0.0,
        )
        self._stream = stream
        self._stream_prices: dict[str, float] = {}

    def execute(self, request: PaperExecutionRequest) -> PaperExecutionResult:
        """Execute a paper order, gating through RiskManager.

        Args:
            request: Paper execution request.

        Returns:
            PaperExecutionResult with risk decision and broker response.
        """
        candidate = self._to_trade_candidate(request)
        decision = self.risk_manager.evaluate(candidate, self.portfolio)
        self.ledger.record_risk_decision(decision)

        if decision.status in (RISK_REJECTED, RISK_KILL_SWITCH_TRIGGERED):
            result = PaperExecutionResult(
                request=request,
                risk_decision=decision,
                broker_response=None,
                reason=f"Risk decision: {decision.status}. Reasons: {'; '.join(decision.reasons)}",
            )
            self._record_execution(result)
            return result

        if decision.status == RISK_REDUCED_SIZE:
            request = PaperExecutionRequest(
                candidate_id=request.candidate_id,
                strategy_name=request.strategy_name,
                symbol=request.symbol,
                quantity=int(decision.final_quantity),
                side=request.side,
                order_type=request.order_type,
                price=request.price,
                signal_metadata=request.signal_metadata,
                timestamp=request.timestamp,
            )

        try:
            broker_response = self.broker_client.submit_paper_order(
                symbol=request.symbol,
                qty=request.quantity,
                side=request.side,
                order_type=request.order_type,
            )
            result = PaperExecutionResult(
                request=request,
                risk_decision=decision,
                broker_response=broker_response,
                reason="Order submitted successfully",
            )
        except Exception as exc:
            result = PaperExecutionResult(
                request=request,
                risk_decision=decision,
                broker_response=None,
                reason=f"Broker error: {type(exc).__name__}: {exc}",
            )

        self._record_execution(result)
        return result

    def _get_latest_price(self, symbol: str) -> Optional[float]:
        """Get latest price from stream or return None.

        Args:
            symbol: Stock symbol to get price for.

        Returns:
            Latest close price from stream, or None if stream not available.
        """
        return self._stream_prices.get(symbol)

    def set_stream_price(self, symbol: str, price: float) -> None:
        """Update the latest price from stream for a symbol.

        Args:
            symbol: Stock symbol
            price: Latest close price
        """
        self._stream_prices[symbol] = price

    def _to_trade_candidate(self, request: PaperExecutionRequest) -> TradeCandidate:
        """Convert paper execution request to trade candidate."""
        return TradeCandidate(
            symbol=request.symbol,
            side=request.side,
            quantity=float(request.quantity),
            price=request.price,
            asset_class="equity",
            strategy_id=request.strategy_name,
            timestamp=request.timestamp,
        )

    def _record_execution(self, result: PaperExecutionResult) -> None:
        """Record execution result to execution log."""
        ledger_path = os.getenv(
            "AURORA_PAPER_LEDGER_PATH",
            "data/paper_ledger/execution_log.jsonl",
        )
        path = Path(ledger_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(result.to_dict(), sort_keys=True) + "\n")
        except OSError:
            pass


def load_ledger_path_from_env() -> str:
    """Load paper ledger path from environment variable."""
    return os.getenv("AURORA_PAPER_LEDGER_PATH", "data/paper_ledger/execution_log.jsonl")