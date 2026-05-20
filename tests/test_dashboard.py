"""Tests for paper trading dashboard."""

import pytest
from unittest.mock import MagicMock, patch

from aurora.monitoring.dashboard import (
    PaperDashboard,
    Position,
    Order,
    Fill,
    RICH_AVAILABLE,
)


def test_dashboard_initialization() -> None:
    """Test dashboard initializes correctly."""
    broker = MagicMock()
    dashboard = PaperDashboard(broker, update_interval=0.5)

    assert dashboard.broker is broker
    assert dashboard.update_interval == 0.5
    assert dashboard._running is False


def test_dashboard_get_account_summary() -> None:
    """Test account summary retrieval."""
    broker = MagicMock()
    broker.get_account.return_value = {
        "cash": "50000.00",
        "portfolio_value": "100000.00",
        "buying_power": "100000.00",
    }

    dashboard = PaperDashboard(broker)
    summary = dashboard._get_account_summary()

    assert summary["Cash"] == "50000.00"
    assert summary["Equity"] == "100000.00"


def test_dashboard_get_positions() -> None:
    """Test position retrieval."""
    broker = MagicMock()
    broker.get_paper_positions.return_value = [
        {"symbol": "AAPL", "qty": 100, "avg_cost": 150.0, "current_price": 155.0},
    ]

    dashboard = PaperDashboard(broker)
    positions = dashboard._get_positions()

    assert len(positions) == 1
    assert positions[0].symbol == "AAPL"
    assert positions[0].quantity == 100
    assert positions[0].unrealized_pnl == 500.0


def test_dashboard_get_pending_orders() -> None:
    """Test pending orders retrieval."""
    broker = MagicMock()
    broker.get_paper_orders.return_value = [
        {"id": "order-123", "symbol": "AAPL", "side": "buy", "qty": 50, "type": "limit", "status": "new"},
    ]

    dashboard = PaperDashboard(broker)
    orders = dashboard._get_pending_orders()

    assert len(orders) == 1
    assert orders[0].symbol == "AAPL"
    assert orders[0].status == "new"


def test_dashboard_calculate_risk() -> None:
    """Test risk calculation."""
    broker = MagicMock()
    dashboard = PaperDashboard(broker)

    positions = [
        Position(symbol="AAPL", quantity=100, avg_price=150.0, market_price=155.0),
        Position(symbol="MSFT", quantity=50, avg_price=300.0, market_price=310.0),
    ]

    risk = dashboard._calculate_risk(positions)

    assert risk["exposure_pct"] > 0
    assert risk["total_pnl"] == 1000.0
    assert risk["open_positions"] == 2


def test_dashboard_start_stop() -> None:
    """Test dashboard start and stop."""
    broker = MagicMock()
    dashboard = PaperDashboard(broker, update_interval=0.01)

    dashboard.start(duration_seconds=1)
    assert dashboard._running is True

    dashboard.stop()
    assert dashboard._running is False


def test_dashboard_with_stream() -> None:
    """Test dashboard with stream."""
    broker = MagicMock()
    stream = MagicMock()

    dashboard = PaperDashboard(broker, stream=stream)

    assert dashboard.stream is stream


def test_dashboard_plain_fallback() -> None:
    """Test plain print fallback works."""
    broker = MagicMock()
    broker.get_account.return_value = {"cash": "10000", "portfolio_value": "10000", "buying_power": "10000"}

    dashboard = PaperDashboard(broker)

    dashboard._print_plain()


def test_dashboard_empty_positions() -> None:
    """Test dashboard handles empty positions."""
    broker = MagicMock()
    broker.get_paper_positions.return_value = []

    dashboard = PaperDashboard(broker)
    positions = dashboard._get_positions()

    assert positions == []


def test_dashboard_exception_handling() -> None:
    """Test dashboard handles broker exceptions."""
    broker = MagicMock()
    broker.get_account.side_effect = Exception("Connection error")

    dashboard = PaperDashboard(broker)
    summary = dashboard._get_account_summary()

    assert summary["Cash"] == "N/A"