import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from aurora.execution.paper_executor import (
    PaperExecutionRequest,
    PaperExecutionResult,
    PaperExecutor,
    load_ledger_path_from_env,
)
from aurora.risk.models import (
    RISK_APPROVED,
    RISK_KILL_SWITCH_TRIGGERED,
    RISK_REDUCED_SIZE,
    RISK_REJECTED,
    PortfolioState,
    RiskDecision,
    RiskConfig,
    TradeCandidate,
)
from aurora.risk.risk_manager import RiskManager


class FakeBrokerClient:
    """Fake broker client for testing."""

    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail
        self.submit_called = False

    def health_check(self) -> dict:
        return {"ok": True}

    def submit_paper_order(self, symbol, qty, side, order_type):
        self.submit_called = True
        if self.should_fail:
            raise Exception("Broker failure")
        return {
            "id": f"order-{symbol}-{qty}-{side}",
            "symbol": symbol,
            "qty": qty,
            "side": side,
            "status": "accepted",
        }

    def cancel_paper_order(self, order_id):
        pass

    def get_paper_positions(self):
        return []

    def get_paper_orders(self):
        return []


def make_approved_decision(candidate: TradeCandidate) -> RiskDecision:
    return RiskDecision(
        status=RISK_APPROVED,
        approved=True,
        original_quantity=candidate.quantity,
        final_quantity=candidate.quantity,
        reasons=["Approved"],
        candidate=candidate,
    )


def make_rejected_decision(candidate: TradeCandidate) -> RiskDecision:
    return RiskDecision(
        status=RISK_REJECTED,
        approved=False,
        original_quantity=candidate.quantity,
        final_quantity=0.0,
        reasons=["Rejected by risk"],
        candidate=candidate,
    )


def make_kill_switch_decision(candidate: TradeCandidate) -> RiskDecision:
    return RiskDecision(
        status=RISK_KILL_SWITCH_TRIGGERED,
        approved=False,
        original_quantity=candidate.quantity,
        final_quantity=0.0,
        reasons=["Kill switch triggered"],
        candidate=candidate,
    )


def test_execute_approved_order_calls_broker() -> None:
    risk_manager = MagicMock()
    risk_manager.evaluate.return_value = make_approved_decision(
        TradeCandidate(symbol="SPY", side="buy", quantity=10, price=100.0)
    )

    broker = FakeBrokerClient()
    executor = PaperExecutor(risk_manager, broker, portfolio=PortfolioState(equity=100000, cash=100000))

    request = PaperExecutionRequest(
        candidate_id="cand-1",
        strategy_name="test-strategy",
        symbol="SPY",
        quantity=10,
        side="buy",
        price=100.0,
    )

    result = executor.execute(request)

    assert result.risk_decision.approved is True
    assert broker.submit_called is True
    assert result.broker_response is not None
    assert "order-" in result.broker_response["id"]


def test_execute_rejected_order_does_not_call_broker() -> None:
    risk_manager = MagicMock()
    risk_manager.evaluate.return_value = make_rejected_decision(
        TradeCandidate(symbol="SPY", side="buy", quantity=10, price=100.0)
    )

    broker = FakeBrokerClient()
    executor = PaperExecutor(risk_manager, broker, portfolio=PortfolioState(equity=100000, cash=100000))

    request = PaperExecutionRequest(
        candidate_id="cand-2",
        strategy_name="test-strategy",
        symbol="SPY",
        quantity=10,
        side="buy",
        price=100.0,
    )

    result = executor.execute(request)

    assert result.risk_decision.approved is False
    assert result.risk_decision.status == RISK_REJECTED
    assert broker.submit_called is False
    assert result.broker_response is None
    assert "REJECTED" in result.reason


def test_execute_kill_switch_does_not_call_broker() -> None:
    risk_manager = MagicMock()
    risk_manager.evaluate.return_value = make_kill_switch_decision(
        TradeCandidate(symbol="SPY", side="buy", quantity=10, price=100.0)
    )

    broker = FakeBrokerClient()
    executor = PaperExecutor(risk_manager, broker, portfolio=PortfolioState(equity=100000, cash=100000))

    request = PaperExecutionRequest(
        candidate_id="cand-3",
        strategy_name="test-strategy",
        symbol="SPY",
        quantity=10,
        side="buy",
        price=100.0,
    )

    result = executor.execute(request)

    assert result.risk_decision.approved is False
    assert result.risk_decision.status == RISK_KILL_SWITCH_TRIGGERED
    assert broker.submit_called is False
    assert result.broker_response is None
    assert "KILL_SWITCH" in result.reason


def test_execute_broker_exception_captured() -> None:
    risk_manager = MagicMock()
    risk_manager.evaluate.return_value = make_approved_decision(
        TradeCandidate(symbol="SPY", side="buy", quantity=10, price=100.0)
    )

    broker = FakeBrokerClient(should_fail=True)
    executor = PaperExecutor(risk_manager, broker, portfolio=PortfolioState(equity=100000, cash=100000))

    request = PaperExecutionRequest(
        candidate_id="cand-4",
        strategy_name="test-strategy",
        symbol="SPY",
        quantity=10,
        side="buy",
        price=100.0,
    )

    result = executor.execute(request)

    assert result.broker_response is None
    assert "Broker error" in result.reason
    assert "Broker failure" in result.reason


def test_execute_records_to_ledger() -> None:
    risk_manager = MagicMock()
    risk_manager.evaluate.return_value = make_approved_decision(
        TradeCandidate(symbol="SPY", side="buy", quantity=10, price=100.0)
    )

    broker = FakeBrokerClient()

    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = os.path.join(tmpdir, "execution_log.jsonl")
        with patch.dict(os.environ, {"AURORA_PAPER_LEDGER_PATH": ledger_path}):
            executor = PaperExecutor(
                risk_manager,
                broker,
                portfolio=PortfolioState(equity=100000, cash=100000),
            )

            request = PaperExecutionRequest(
                candidate_id="cand-5",
                strategy_name="test-strategy",
                symbol="SPY",
                quantity=10,
                side="buy",
                price=100.0,
            )
            executor.execute(request)

            with open(ledger_path) as f:
                lines = f.readlines()
                assert len(lines) == 1
                record = json.loads(lines[0])
                assert record["request"]["candidate_id"] == "cand-5"
                assert record["risk_decision"]["status"] == RISK_APPROVED


def test_execute_rejected_records_to_ledger() -> None:
    risk_manager = MagicMock()
    risk_manager.evaluate.return_value = make_rejected_decision(
        TradeCandidate(symbol="SPY", side="buy", quantity=10, price=100.0)
    )

    broker = FakeBrokerClient()

    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = os.path.join(tmpdir, "execution_log.jsonl")
        with patch.dict(os.environ, {"AURORA_PAPER_LEDGER_PATH": ledger_path}):
            executor = PaperExecutor(
                risk_manager,
                broker,
                portfolio=PortfolioState(equity=100000, cash=100000),
            )

            request = PaperExecutionRequest(
                candidate_id="cand-6",
                strategy_name="test-strategy",
                symbol="SPY",
                quantity=10,
                side="buy",
                price=100.0,
            )
            executor.execute(request)

            with open(ledger_path) as f:
                lines = f.readlines()
                assert len(lines) == 1
                record = json.loads(lines[0])
                assert record["request"]["candidate_id"] == "cand-6"
                assert record["risk_decision"]["status"] == RISK_REJECTED
                assert record["broker_response"] is None


def test_load_ledger_path_from_env_default() -> None:
    with patch.dict(os.environ, {}, clear=True):
        path = load_ledger_path_from_env()
        assert path == "data/paper_ledger/execution_log.jsonl"


def test_load_ledger_path_from_env_custom() -> None:
    with patch.dict(os.environ, {"AURORA_PAPER_LEDGER_PATH": "/custom/path/log.jsonl"}):
        path = load_ledger_path_from_env()
        assert path == "/custom/path/log.jsonl"


def test_result_to_dict_contains_no_secrets() -> None:
    candidate = TradeCandidate(symbol="SPY", side="buy", quantity=10, price=100.0)
    decision = make_approved_decision(candidate)

    request = PaperExecutionRequest(
        candidate_id="cand-7",
        strategy_name="test-strategy",
        symbol="SPY",
        quantity=10,
        side="buy",
        price=100.0,
    )

    result = PaperExecutionResult(
        request=request,
        risk_decision=decision,
        broker_response={"id": "order-123", "status": "accepted"},
        reason="Success",
    )

    result_dict = result.to_dict()
    assert "cand-7" in str(result_dict)
    assert "test-strategy" in str(result_dict)
    assert "SPY" in str(result_dict)
    assert "order-123" in str(result_dict)