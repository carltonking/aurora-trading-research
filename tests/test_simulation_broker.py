import pytest

from aurora.execution.ledger import PaperLedger
from aurora.execution.models import ORDER_FILLED, ORDER_REJECTED
from aurora.execution.simulation_broker import SimulationBroker
from aurora.risk.models import (
    RISK_KILL_SWITCH_TRIGGERED,
    RISK_REDUCED_SIZE,
    RISK_REJECTED,
    RiskConfig,
    TradeCandidate,
)
from aurora.risk.risk_manager import RiskManager


def _broker(tmp_path, config: RiskConfig | None = None, starting_cash: float = 100000.0) -> SimulationBroker:
    return SimulationBroker(
        starting_cash=starting_cash,
        risk_manager=RiskManager(config or RiskConfig()),
        ledger=PaperLedger(tmp_path),
        slippage_bps=0.0,
    )


def test_buy_candidate_is_risk_checked_filled_cash_reduced_and_position_created(tmp_path) -> None:
    broker = _broker(tmp_path)

    order = broker.submit_candidate(TradeCandidate(symbol="AAPL", side="buy", quantity=10, price=100))

    assert order.status == ORDER_FILLED
    assert broker.get_account().cash == pytest.approx(99000.0)
    assert broker.get_positions()["AAPL"].quantity == pytest.approx(10.0)
    assert len(broker.ledger.list_risk_decisions()) == 1
    assert len(broker.ledger.list_orders()) == 1


def test_oversized_buy_reduced_by_risk_manager_and_filled(tmp_path) -> None:
    broker = _broker(tmp_path)

    order = broker.submit_candidate(TradeCandidate(symbol="AAPL", side="buy", quantity=1000, price=100))

    assert order.status == ORDER_FILLED
    assert order.risk_status == RISK_REDUCED_SIZE
    assert order.quantity == pytest.approx(50.0)


def test_rejected_candidate_is_recorded_as_rejected(tmp_path) -> None:
    broker = _broker(tmp_path)

    order = broker.submit_candidate(
        TradeCandidate(symbol="BTC", side="buy", quantity=1, price=100, asset_class="crypto")
    )

    assert order.status == ORDER_REJECTED
    assert order.risk_status == RISK_REJECTED
    assert broker.ledger.list_orders()[0]["status"] == ORDER_REJECTED


def test_sell_candidate_reduces_position(tmp_path) -> None:
    broker = _broker(tmp_path)
    broker.submit_candidate(TradeCandidate(symbol="AAPL", side="buy", quantity=10, price=100))

    order = broker.submit_candidate(TradeCandidate(symbol="AAPL", side="sell", quantity=4, price=110))

    assert order.status == ORDER_FILLED
    assert broker.get_positions()["AAPL"].quantity == pytest.approx(6.0)
    assert broker.get_account().cash == pytest.approx(99440.0)


def test_sell_without_position_is_rejected(tmp_path) -> None:
    broker = _broker(tmp_path)

    order = broker.submit_candidate(TradeCandidate(symbol="AAPL", side="sell", quantity=1, price=100))

    assert order.status == ORDER_REJECTED
    assert order.risk_status == RISK_REJECTED


def test_mark_to_market_updates_market_value_and_equity(tmp_path) -> None:
    broker = _broker(tmp_path)
    broker.submit_candidate(TradeCandidate(symbol="AAPL", side="buy", quantity=10, price=100))

    account = broker.mark_to_market({"AAPL": 120.0})

    assert account.market_value == pytest.approx(1200.0)
    assert account.equity == pytest.approx(100200.0)


def test_reset_clears_state(tmp_path) -> None:
    broker = _broker(tmp_path)
    broker.submit_candidate(TradeCandidate(symbol="AAPL", side="buy", quantity=10, price=100))

    broker.reset()

    assert broker.get_account().cash == pytest.approx(100000.0)
    assert broker.get_account().market_value == pytest.approx(0.0)
    assert broker.get_positions() == {}


def test_kill_switch_causes_rejected_order_with_kill_switch_risk_status(tmp_path) -> None:
    broker = _broker(tmp_path, RiskConfig(kill_switch_enabled=True))

    order = broker.submit_candidate(TradeCandidate(symbol="AAPL", side="buy", quantity=10, price=100))

    assert order.status == ORDER_REJECTED
    assert order.risk_status == RISK_KILL_SWITCH_TRIGGERED
