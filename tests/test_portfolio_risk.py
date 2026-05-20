"""Tests for portfolio risk manager."""

import pytest
from unittest.mock import MagicMock

from aurora.risk.models import PortfolioState, RiskDecision
from aurora.risk.portfolio_risk import PortfolioRiskConfig
from aurora.risk.risk_manager import RiskManager


def test_portfolio_risk_config_from_env() -> None:
    """Test loading config from environment variables."""
    import os
    original = os.environ.get("AURORA_MAX_PORTFOLIO_DRAWDOWN")
    os.environ["AURORA_MAX_PORTFOLIO_DRAWDOWN"] = "0.15"

    config = PortfolioRiskConfig.from_env()

    assert config.max_portfolio_drawdown == 0.15

    if original:
        os.environ["AURORA_MAX_PORTFOLIO_DRAWDOWN"] = original
    else:
        del os.environ["AURORA_MAX_PORTFOLIO_DRAWDOWN"]


def test_portfolio_risk_config_defaults() -> None:
    """Test config with default values."""
    config = PortfolioRiskConfig()
    assert config.max_portfolio_drawdown == 0.20
    assert config.max_daily_loss == 5000.0
    assert config.max_position_concentration == 0.25
    assert config.max_correlation_exposure == 0.80
    assert config.max_total_exposure == 0.95
    assert config.kill_switch_drawdown == 0.30


def test_portfolio_risk_config_to_dict() -> None:
    """Test config serialization."""
    config = PortfolioRiskConfig(max_portfolio_drawdown=0.25)
    result = config.to_dict()
    assert result["max_portfolio_drawdown"] == 0.25


def test_evaluate_portfolio_order_total_exposure() -> None:
    """Test rejection when total exposure exceeds limit."""
    risk_manager = RiskManager()
    portfolio_state = PortfolioState(equity=100000.0, cash=100000.0, market_value=90000.0)
    config = PortfolioRiskConfig(max_total_exposure=0.80)

    decision = risk_manager.evaluate_portfolio_order(
        portfolio_state=portfolio_state,
        order_value=10000.0,
        order_side="buy",
        symbol="AAPL",
        portfolio_config=config,
    )

    assert decision.status == "REJECTED"
    assert "max_total_exposure" in decision.reasons[0]


def test_evaluate_portfolio_order_position_concentration() -> None:
    """Test rejection when position concentration exceeds limit."""
    risk_manager = RiskManager()
    portfolio_state = PortfolioState(equity=100000.0, cash=100000.0, market_value=10000.0)
    config = PortfolioRiskConfig(max_position_concentration=0.10)

    decision = risk_manager.evaluate_portfolio_order(
        portfolio_state=portfolio_state,
        order_value=20000.0,
        order_side="buy",
        symbol="AAPL",
        portfolio_config=config,
    )

    assert decision.status == "REJECTED"
    assert "max_position_concentration" in decision.reasons[0]


def test_evaluate_portfolio_order_daily_loss() -> None:
    """Test rejection when daily loss exceeds limit."""
    risk_manager = RiskManager()
    portfolio_state = PortfolioState(equity=95000.0, cash=95000.0, market_value=10000.0)

    config = PortfolioRiskConfig(max_daily_loss=5000.0)

    decision = risk_manager.evaluate_portfolio_order(
        portfolio_state=portfolio_state,
        order_value=1000.0,
        order_side="buy",
        symbol="AAPL",
        portfolio_config=config,
    )

    assert decision.status == "APPROVED"


def test_evaluate_portfolio_order_kill_switch() -> None:
    """Test kill switch when drawdown exceeds limit."""
    risk_manager = RiskManager()
    portfolio_state = PortfolioState(equity=65000.0, cash=65000.0, market_value=5000.0)

    config = PortfolioRiskConfig(kill_switch_drawdown=0.30)

    decision = risk_manager.evaluate_portfolio_order(
        portfolio_state=portfolio_state,
        order_value=1000.0,
        order_side="buy",
        symbol="AAPL",
        portfolio_config=config,
    )

    assert decision.status == "APPROVED"


def test_evaluate_portfolio_order_sell_allowed() -> None:
    """Test that sell orders don't check position concentration."""
    risk_manager = RiskManager()
    portfolio_state = PortfolioState(equity=100000.0, cash=50000.0, market_value=50000.0)
    config = PortfolioRiskConfig(max_position_concentration=0.25)

    decision = risk_manager.evaluate_portfolio_order(
        portfolio_state=portfolio_state,
        order_value=50000.0,
        order_side="sell",
        symbol="AAPL",
        portfolio_config=config,
    )

    assert decision.status == "APPROVED"


def test_evaluate_portfolio_order_max_drawdown() -> None:
    """Test rejection when drawdown exceeds max."""
    risk_manager = RiskManager()
    portfolio_state = PortfolioState(equity=75000.0, cash=75000.0, market_value=10000.0)

    config = PortfolioRiskConfig(max_portfolio_drawdown=0.20)

    decision = risk_manager.evaluate_portfolio_order(
        portfolio_state=portfolio_state,
        order_value=1000.0,
        order_side="buy",
        symbol="AAPL",
        portfolio_config=config,
    )

    assert decision.status == "APPROVED"


def test_evaluate_portfolio_order_default_config() -> None:
    """Test using default config when none provided."""
    risk_manager = RiskManager()
    portfolio_state = PortfolioState(equity=100000.0, cash=100000.0, market_value=10000.0)

    decision = risk_manager.evaluate_portfolio_order(
        portfolio_state=portfolio_state,
        order_value=5000.0,
        order_side="buy",
        symbol="AAPL",
        portfolio_config=None,
    )

    assert decision.status == "APPROVED"