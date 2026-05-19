from aurora.execution.ledger import PaperLedger
from aurora.execution.models import ORDER_FILLED, SimulatedAccount, SimulatedOrder, SimulatedPosition
from aurora.risk.models import RISK_APPROVED, RiskDecision, TradeCandidate


def _order() -> SimulatedOrder:
    return SimulatedOrder(
        order_id="sim_000001",
        symbol="AAPL",
        side="buy",
        quantity=10.0,
        requested_quantity=10.0,
        price=100.0,
        fill_price=100.0,
        status=ORDER_FILLED,
        timestamp="2024-01-01T00:00:00+00:00",
        strategy_id=None,
        risk_status=RISK_APPROVED,
        risk_reasons=["approved"],
    )


def _decision() -> RiskDecision:
    candidate = TradeCandidate(symbol="AAPL", side="buy", quantity=10.0, price=100.0)
    return RiskDecision(
        status=RISK_APPROVED,
        approved=True,
        original_quantity=10.0,
        final_quantity=10.0,
        reasons=["approved"],
        candidate=candidate,
    )


def test_record_order_appends_jsonl(tmp_path) -> None:
    ledger = PaperLedger(tmp_path)

    ledger.record_order(_order())
    ledger.record_order(_order())

    orders = ledger.list_orders()
    assert len(orders) == 2
    assert orders[0]["order_id"] == "sim_000001"


def test_record_risk_decision_appends_jsonl(tmp_path) -> None:
    ledger = PaperLedger(tmp_path)

    ledger.record_risk_decision(_decision())

    decisions = ledger.list_risk_decisions()
    assert len(decisions) == 1
    assert decisions[0]["candidate"]["symbol"] == "AAPL"


def test_save_load_account_round_trips(tmp_path) -> None:
    ledger = PaperLedger(tmp_path)
    account = SimulatedAccount(equity=100000.0, cash=99000.0, market_value=1000.0)

    ledger.save_account(account)

    assert ledger.load_account() == account


def test_save_load_positions_round_trips(tmp_path) -> None:
    ledger = PaperLedger(tmp_path)
    positions = {"AAPL": SimulatedPosition(symbol="AAPL", quantity=10.0, average_price=100.0)}

    ledger.save_positions(positions)

    assert ledger.load_positions() == positions


def test_missing_account_and_positions_return_empty_state(tmp_path) -> None:
    ledger = PaperLedger(tmp_path)

    assert ledger.load_account() is None
    assert ledger.load_positions() == {}
