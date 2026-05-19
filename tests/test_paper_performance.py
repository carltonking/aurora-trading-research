import json
import tempfile
from pathlib import Path

import pytest

from aurora.analysis.paper_performance import (
    PaperMetrics,
    PaperPerformanceAnalyzer,
    save_metrics,
)


def create_test_ledger(base_path: Path, trades: list[dict]) -> Path:
    ledger_path = base_path / "execution_log.jsonl"
    with ledger_path.open("w", encoding="utf-8") as f:
        for trade in trades:
            f.write(json.dumps(trade) + "\n")
    return ledger_path


def test_load_trades_filters_approved_only() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)

        trades = [
            {
                "request": {"strategy_name": "test", "symbol": "SPY", "quantity": 10, "side": "buy", "price": 100.0, "timestamp": "2024-01-01T10:00:00Z"},
                "risk_decision": {"status": "APPROVED", "approved": True, "final_quantity": 10, "reasons": ["ok"]},
                "broker_response": {"id": "order-1"},
                "reason": "success",
            },
            {
                "request": {"strategy_name": "test", "symbol": "SPY", "quantity": 10, "side": "buy", "price": 100.0, "timestamp": "2024-01-02T10:00:00Z"},
                "risk_decision": {"status": "REJECTED", "approved": False, "final_quantity": 0, "reasons": ["rejected"]},
                "broker_response": None,
                "reason": "rejected",
            },
            {
                "request": {"strategy_name": "test", "symbol": "SPY", "quantity": 10, "side": "sell", "price": 100.0, "timestamp": "2024-01-03T10:00:00Z"},
                "risk_decision": {"status": "APPROVED", "approved": True, "final_quantity": 10, "reasons": ["ok"]},
                "broker_response": {"id": "order-2"},
                "reason": "success",
            },
        ]

        ledger_path = create_test_ledger(base_path, trades)
        analyzer = PaperPerformanceAnalyzer(ledger_path=str(ledger_path))

        loaded = analyzer.load_trades()
        assert len(loaded) == 2


def test_compute_metrics_win_rate() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)

        trades = [
            {
                "request": {"strategy_name": "test", "symbol": "SPY", "quantity": 10, "side": "buy", "price": 100.0, "timestamp": "2024-01-01T10:00:00Z"},
                "risk_decision": {"status": "APPROVED", "approved": True, "final_quantity": 10, "reasons": ["ok"]},
                "broker_response": {"id": "order-1"},
                "reason": "success",
            },
            {
                "request": {"strategy_name": "test", "symbol": "SPY", "quantity": 10, "side": "buy", "price": 100.0, "timestamp": "2024-01-02T10:00:00Z"},
                "risk_decision": {"status": "APPROVED", "approved": True, "final_quantity": 10, "reasons": ["ok"]},
                "broker_response": {"id": "order-2"},
                "reason": "success",
            },
        ]

        ledger_path = create_test_ledger(base_path, trades)
        analyzer = PaperPerformanceAnalyzer(ledger_path=str(ledger_path))

        metrics = analyzer.compute_metrics()

        assert metrics.total_trades == 2
        assert metrics.win_count + metrics.loss_count == 2


def test_compute_metrics_zero_trades() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)

        trades = [
            {
                "request": {"strategy_name": "test", "symbol": "SPY", "quantity": 10, "side": "buy", "price": 100.0, "timestamp": "2024-01-01T10:00:00Z"},
                "risk_decision": {"status": "REJECTED", "approved": False, "final_quantity": 0, "reasons": ["rejected"]},
                "broker_response": None,
                "reason": "rejected",
            },
        ]

        ledger_path = create_test_ledger(base_path, trades)
        analyzer = PaperPerformanceAnalyzer(ledger_path=str(ledger_path))

        metrics = analyzer.compute_metrics()

        assert metrics.total_trades == 0


def test_compute_metrics_filter_by_strategy() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)

        trades = [
            {
                "request": {"strategy_name": "strategy_a", "symbol": "SPY", "quantity": 10, "side": "buy", "price": 100.0, "timestamp": "2024-01-01T10:00:00Z"},
                "risk_decision": {"status": "APPROVED", "approved": True, "final_quantity": 10, "reasons": ["ok"]},
                "broker_response": {"id": "order-1"},
                "reason": "success",
            },
            {
                "request": {"strategy_name": "strategy_b", "symbol": "SPY", "quantity": 10, "side": "buy", "price": 100.0, "timestamp": "2024-01-02T10:00:00Z"},
                "risk_decision": {"status": "APPROVED", "approved": True, "final_quantity": 10, "reasons": ["ok"]},
                "broker_response": {"id": "order-2"},
                "reason": "success",
            },
        ]

        ledger_path = create_test_ledger(base_path, trades)
        analyzer = PaperPerformanceAnalyzer(ledger_path=str(ledger_path))

        metrics_a = analyzer.compute_metrics(strategy_name="strategy_a")
        assert metrics_a.total_trades == 1
        assert metrics_a.strategy_name == "strategy_a"


def test_metrics_to_dict() -> None:
    metrics = PaperMetrics(
        strategy_name="test_strategy",
        total_trades=10,
        win_count=6,
        loss_count=4,
        win_rate=0.6,
        total_pnl=100.0,
    )

    result = metrics.to_dict()

    assert result["strategy_name"] == "test_strategy"
    assert result["total_trades"] == 10
    assert result["win_rate"] == 0.6


def test_save_metrics() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        metrics = PaperMetrics(
            strategy_name="test",
            total_trades=5,
            win_rate=0.6,
        )

        output_path = save_metrics(metrics, tmpdir)

        assert output_path.exists()

        with output_path.open() as f:
            loaded = json.load(f)

        assert loaded["strategy_name"] == "test"
        assert loaded["total_trades"] == 5