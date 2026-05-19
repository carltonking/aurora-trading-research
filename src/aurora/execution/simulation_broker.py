"""Local risk-gated simulation broker."""

from dataclasses import replace
from datetime import UTC, datetime

from aurora.execution.exceptions import BrokerExecutionError
from aurora.execution.ledger import PaperLedger
from aurora.execution.models import (
    ORDER_FILLED,
    ORDER_REJECTED,
    SimulatedAccount,
    SimulatedOrder,
    SimulatedPosition,
)
from aurora.risk.models import PortfolioState, TradeCandidate
from aurora.risk.risk_manager import RiskManager


class SimulationBroker:
    """Local-only broker simulator that never places real orders."""

    name = "simulation"

    def __init__(
        self,
        starting_cash: float = 100000.0,
        risk_manager: RiskManager | None = None,
        ledger: PaperLedger | None = None,
        slippage_bps: float = 5.0,
    ) -> None:
        if starting_cash <= 0:
            raise BrokerExecutionError("starting_cash must be greater than 0.")
        if slippage_bps < 0:
            raise BrokerExecutionError("slippage_bps must be non-negative.")

        self.starting_cash = float(starting_cash)
        self.risk_manager = risk_manager or RiskManager()
        self.ledger = ledger or PaperLedger()
        self.slippage_bps = slippage_bps
        self.account = self.ledger.load_account() or SimulatedAccount(
            equity=self.starting_cash,
            cash=self.starting_cash,
            market_value=0.0,
        )
        self.positions = self.ledger.load_positions()
        self.trades_today = 0
        self.last_trade_timestamps: dict[str, str] = {}

    def is_live(self) -> bool:
        """Return whether this broker performs live trading."""
        return False

    def get_account(self) -> SimulatedAccount:
        """Return current simulated account state."""
        return self.account

    def get_positions(self) -> dict[str, SimulatedPosition]:
        """Return current simulated positions."""
        return dict(self.positions)

    def mark_to_market(self, prices: dict[str, float]) -> SimulatedAccount:
        """Update account equity from current market prices."""
        updated_positions: dict[str, SimulatedPosition] = {}
        market_value = 0.0
        for symbol, position in self.positions.items():
            market_price = float(prices.get(symbol, position.market_price or position.average_price))
            market_value += position.quantity * market_price
            updated_positions[symbol] = replace(position, market_price=market_price)
        self.positions = updated_positions
        self.account = replace(
            self.account,
            market_value=market_value,
            equity=self.account.cash + market_value,
        )
        self.ledger.save_account(self.account)
        self.ledger.save_positions(self.positions)
        return self.account

    def submit_candidate(self, candidate: TradeCandidate) -> SimulatedOrder:
        """Risk-check and locally simulate a trade candidate."""
        candidate = self._with_timestamp(candidate)
        decision = self.risk_manager.evaluate(candidate, self._portfolio_state())
        self.ledger.record_risk_decision(decision)

        if not decision.approved:
            order = self._rejected_order(candidate, decision.status, decision.reasons)
            self.ledger.record_order(order)
            return order

        quantity = decision.final_quantity
        if candidate.side == "buy":
            order = self._fill_buy(candidate, quantity, decision.status, decision.reasons)
        elif candidate.side == "sell":
            order = self._fill_sell(candidate, quantity, decision.status, decision.reasons)
        else:
            raise BrokerExecutionError(f"Unsupported side after risk evaluation: {candidate.side}")

        self.ledger.record_order(order)
        self.ledger.save_account(self.account)
        self.ledger.save_positions(self.positions)
        self.trades_today += 1
        self.last_trade_timestamps[candidate.symbol] = candidate.timestamp or order.timestamp
        return order

    def reset(self) -> None:
        """Reset in-memory simulated account and positions."""
        self.account = SimulatedAccount(
            equity=self.starting_cash,
            cash=self.starting_cash,
            market_value=0.0,
        )
        self.positions = {}
        self.trades_today = 0
        self.last_trade_timestamps = {}
        self.ledger.save_account(self.account)
        self.ledger.save_positions(self.positions)

    def _fill_buy(
        self,
        candidate: TradeCandidate,
        quantity: float,
        risk_status: str,
        risk_reasons: list[str],
    ) -> SimulatedOrder:
        fill_price = self._buy_price(candidate.price)
        total_cost = quantity * fill_price
        if quantity <= 0 or total_cost > self.account.cash:
            return self._rejected_order(
                candidate,
                risk_status,
                [*risk_reasons, "Broker guard rejected buy because cash is insufficient after slippage."],
            )

        existing = self.positions.get(candidate.symbol)
        if existing is None:
            new_position = SimulatedPosition(
                symbol=candidate.symbol,
                quantity=quantity,
                average_price=fill_price,
                market_price=fill_price,
            )
        else:
            combined_quantity = existing.quantity + quantity
            average_price = (
                existing.average_price * existing.quantity + fill_price * quantity
            ) / combined_quantity
            new_position = SimulatedPosition(
                symbol=candidate.symbol,
                quantity=combined_quantity,
                average_price=average_price,
                market_price=fill_price,
            )
        self.positions[candidate.symbol] = new_position
        self.account = replace(self.account, cash=self.account.cash - total_cost)
        self._refresh_account()
        return self._filled_order(candidate, quantity, fill_price, risk_status, risk_reasons)

    def _fill_sell(
        self,
        candidate: TradeCandidate,
        quantity: float,
        risk_status: str,
        risk_reasons: list[str],
    ) -> SimulatedOrder:
        position = self.positions.get(candidate.symbol)
        if position is None or position.quantity < quantity:
            return self._rejected_order(
                candidate,
                risk_status,
                [*risk_reasons, "Broker guard rejected sell because position quantity is insufficient."],
            )

        fill_price = self._sell_price(candidate.price)
        proceeds = quantity * fill_price
        remaining_quantity = position.quantity - quantity
        if remaining_quantity <= 1e-12:
            self.positions.pop(candidate.symbol)
        else:
            self.positions[candidate.symbol] = SimulatedPosition(
                symbol=candidate.symbol,
                quantity=remaining_quantity,
                average_price=position.average_price,
                market_price=fill_price,
            )
        self.account = replace(self.account, cash=self.account.cash + proceeds)
        self._refresh_account()
        return self._filled_order(candidate, quantity, fill_price, risk_status, risk_reasons)

    def _refresh_account(self) -> None:
        market_value = sum(
            position.quantity * (position.market_price or position.average_price)
            for position in self.positions.values()
        )
        self.account = replace(
            self.account,
            market_value=market_value,
            equity=self.account.cash + market_value,
        )

    def _portfolio_state(self) -> PortfolioState:
        return PortfolioState(
            equity=self.account.equity,
            cash=self.account.cash,
            market_value=self.account.market_value,
            daily_pnl=self.account.daily_pnl,
            weekly_pnl=self.account.weekly_pnl,
            open_positions={symbol: position.quantity for symbol, position in self.positions.items()},
            trades_today=self.trades_today,
            last_trade_timestamps=dict(self.last_trade_timestamps),
        )

    def _filled_order(
        self,
        candidate: TradeCandidate,
        quantity: float,
        fill_price: float,
        risk_status: str,
        risk_reasons: list[str],
    ) -> SimulatedOrder:
        return SimulatedOrder(
            order_id=self._next_order_id(),
            symbol=candidate.symbol,
            side=candidate.side,
            quantity=quantity,
            requested_quantity=candidate.quantity,
            price=candidate.price,
            fill_price=fill_price,
            status=ORDER_FILLED,
            timestamp=candidate.timestamp or _utc_now(),
            strategy_id=candidate.strategy_id,
            risk_status=risk_status,
            risk_reasons=risk_reasons,
        )

    def _rejected_order(
        self,
        candidate: TradeCandidate,
        risk_status: str,
        risk_reasons: list[str],
    ) -> SimulatedOrder:
        return SimulatedOrder(
            order_id=self._next_order_id(),
            symbol=candidate.symbol,
            side=candidate.side,
            quantity=0.0,
            requested_quantity=candidate.quantity,
            price=candidate.price,
            fill_price=None,
            status=ORDER_REJECTED,
            timestamp=candidate.timestamp or _utc_now(),
            strategy_id=candidate.strategy_id,
            risk_status=risk_status,
            risk_reasons=risk_reasons,
        )

    def _with_timestamp(self, candidate: TradeCandidate) -> TradeCandidate:
        if candidate.timestamp:
            return candidate
        return replace(candidate, timestamp=_utc_now())

    def _next_order_id(self) -> str:
        return f"sim_{len(self.ledger.list_orders()) + 1:06d}"

    def _buy_price(self, price: float) -> float:
        return price * (1 + self.slippage_bps / 10000)

    def _sell_price(self, price: float) -> float:
        return price * (1 - self.slippage_bps / 10000)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
