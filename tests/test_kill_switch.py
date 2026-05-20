"""Tests for kill-switch system."""

import pytest

from aurora.risk.kill_switch import (
    KillSwitch,
    KillSwitchConfig,
    KillSwitchMetrics,
    get_kill_switch_config_from_env,
)
from aurora.risk.models import RISK_KILL_SWITCH_TRIGGERED


def test_kill_switch_default_active() -> None:
    """Test kill-switch starts in active state."""
    config = KillSwitchConfig()
    ks = KillSwitch(config)
    assert ks.is_active() is False
    assert ks.trigger_reason is None


def test_kill_switch_max_drawdown_trigger() -> None:
    """Test max drawdown trigger."""
    config = KillSwitchConfig(max_portfolio_drawdown=0.2)
    ks = KillSwitch(config)

    metrics = KillSwitchMetrics(drawdown=0.25, peak_equity=100000, current_equity=75000)

    assert ks.evaluate(metrics) is True
    assert ks.trigger_reason is not None
    assert "max_drawdown" in ks.trigger_reason


def test_kill_switch_max_drawdown_no_trigger() -> None:
    """Test max drawdown not triggered when below threshold."""
    config = KillSwitchConfig(max_portfolio_drawdown=0.3)
    ks = KillSwitch(config)

    metrics = KillSwitchMetrics(drawdown=0.2, peak_equity=100000, current_equity=80000)

    assert ks.evaluate(metrics) is False


def test_kill_switch_max_daily_loss_trigger() -> None:
    """Test max daily loss trigger."""
    config = KillSwitchConfig(max_daily_loss=5000)
    ks = KillSwitch(config)

    metrics = KillSwitchMetrics(daily_loss=6000)

    assert ks.evaluate(metrics) is True
    assert "daily_loss" in ks.trigger_reason


def test_kill_switch_max_daily_loss_no_trigger() -> None:
    """Test max daily loss not triggered when below threshold."""
    config = KillSwitchConfig(max_daily_loss=5000)
    ks = KillSwitch(config)

    metrics = KillSwitchMetrics(daily_loss=4000)

    assert ks.evaluate(metrics) is False


def test_kill_switch_min_sharpe_trigger() -> None:
    """Test min Sharpe trigger."""
    config = KillSwitchConfig(min_sharpe=0.5)
    ks = KillSwitch(config)

    metrics = KillSwitchMetrics(rolling_sharpe=0.3)

    assert ks.evaluate(metrics) is True
    assert "sharpe" in ks.trigger_reason


def test_kill_switch_min_sharpe_no_trigger() -> None:
    """Test min Sharpe not triggered when above threshold."""
    config = KillSwitchConfig(min_sharpe=0.5)
    ks = KillSwitch(config)

    metrics = KillSwitchMetrics(rolling_sharpe=0.7)

    assert ks.evaluate(metrics) is False


def test_kill_switch_consecutive_losses_trigger() -> None:
    """Test consecutive losses trigger."""
    config = KillSwitchConfig(max_consecutive_losses=3)
    ks = KillSwitch(config)

    metrics = KillSwitchMetrics(consecutive_losses=4)

    assert ks.evaluate(metrics) is True
    assert "consecutive_losses" in ks.trigger_reason


def test_kill_switch_consecutive_losses_no_trigger() -> None:
    """Test consecutive losses not triggered when below threshold."""
    config = KillSwitchConfig(max_consecutive_losses=5)
    ks = KillSwitch(config)

    metrics = KillSwitchMetrics(consecutive_losses=3)

    assert ks.evaluate(metrics) is False


def test_kill_switch_emergency_kill_trigger() -> None:
    """Test emergency kill trigger."""
    config = KillSwitchConfig(emergency_kill=True)
    ks = KillSwitch(config)

    metrics = KillSwitchMetrics()

    assert ks.evaluate(metrics) is True
    assert "emergency_kill" in ks.trigger_reason


def test_kill_switch_multiple_triggers() -> None:
    """Test multiple conditions trigger together."""
    config = KillSwitchConfig(
        max_portfolio_drawdown=0.2,
        max_daily_loss=5000,
    )
    ks = KillSwitch(config)

    metrics = KillSwitchMetrics(drawdown=0.25, daily_loss=6000)

    assert ks.evaluate(metrics) is True
    assert "max_drawdown" in ks.trigger_reason
    assert "daily_loss" in ks.trigger_reason


def test_kill_switch_activate_manual() -> None:
    """Test manual activation."""
    config = KillSwitchConfig()
    ks = KillSwitch(config)

    ks.activate("manual_override")
    assert ks.is_active() is True
    assert ks.trigger_reason == "manual_override"


def test_kill_switch_deactivate() -> None:
    """Test deactivation."""
    config = KillSwitchConfig(max_portfolio_drawdown=0.1)
    ks = KillSwitch(config)

    metrics = KillSwitchMetrics(drawdown=0.15)
    if ks.evaluate(metrics):
        ks.activate(ks.trigger_reason)
    assert ks.is_active() is True

    ks.deactivate()
    assert ks.is_active() is False
    assert ks.trigger_reason is None


def test_kill_switch_all_disabled() -> None:
    """Test with all triggers disabled."""
    config = KillSwitchConfig()
    ks = KillSwitch(config)

    metrics = KillSwitchMetrics(
        drawdown=0.9,
        daily_loss=100000,
        rolling_sharpe=-10.0,
        consecutive_losses=100,
    )

    assert ks.evaluate(metrics) is False


def test_get_kill_switch_config_from_env_defaults() -> None:
    """Test config from environment with defaults."""
    import os

    for key in [
        "AURORA_KS_MAX_DRAWDOWN",
        "AURORA_KS_MAX_DAILY_LOSS",
        "AURORA_KS_MIN_SHARPE",
        "AURORA_KS_MAX_CONSECUTIVE_LOSSES",
        "AURORA_KS_EMERGENCY_KILL",
    ]:
        if key in os.environ:
            del os.environ[key]

    config = get_kill_switch_config_from_env()

    assert config.max_portfolio_drawdown is None
    assert config.max_daily_loss is None
    assert config.min_sharpe is None
    assert config.max_consecutive_losses is None
    assert config.emergency_kill is False


def test_get_kill_switch_config_from_env_values() -> None:
    """Test config from environment with values."""
    import os

    os.environ["AURORA_KS_MAX_DRAWDOWN"] = "0.2"
    os.environ["AURORA_KS_MAX_DAILY_LOSS"] = "5000"
    os.environ["AURORA_KS_MIN_SHARPE"] = "0.5"
    os.environ["AURORA_KS_MAX_CONSECUTIVE_LOSSES"] = "5"
    os.environ["AURORA_KS_EMERGENCY_KILL"] = "true"

    try:
        config = get_kill_switch_config_from_env()

        assert config.max_portfolio_drawdown == 0.2
        assert config.max_daily_loss == 5000.0
        assert config.min_sharpe == 0.5
        assert config.max_consecutive_losses == 5
        assert config.emergency_kill is True
    finally:
        for key in [
            "AURORA_KS_MAX_DRAWDOWN",
            "AURORA_KS_MAX_DAILY_LOSS",
            "AURORA_KS_MIN_SHARPE",
            "AURORA_KS_MAX_CONSECUTIVE_LOSSES",
            "AURORA_KS_EMERGENCY_KILL",
        ]:
            if key in os.environ:
                del os.environ[key]


def test_kill_switch_integration_with_executor() -> None:
    """Test kill-switch integration with PaperExecutor."""
    from unittest.mock import MagicMock

    from aurora.execution.paper_executor import (
        PaperExecutionRequest,
        PaperExecutionResult,
    )
    from aurora.risk.kill_switch import KillSwitch, KillSwitchConfig

    config = KillSwitchConfig(emergency_kill=True)
    ks = KillSwitch(config)

    if ks.evaluate(KillSwitchMetrics()):
        ks.activate(ks.trigger_reason)
    assert ks.is_active() is True

    mock_rm = MagicMock()
    mock_candidate = MagicMock()
    mock_candidate.symbol = "AAPL"
    mock_rm.evaluate.return_value = MagicMock(
        status=RISK_KILL_SWITCH_TRIGGERED,
        approved=False,
        original_quantity=10.0,
        final_quantity=0.0,
        reasons=["kill_switch"],
        candidate=mock_candidate,
    )
    mock_broker = MagicMock()

    from aurora.execution.paper_executor import PaperExecutor

    executor = PaperExecutor(
        risk_manager=mock_rm,
        broker_client=mock_broker,
        kill_switch=ks,
    )

    request = PaperExecutionRequest(
        candidate_id="test-1",
        strategy_name="test_strategy",
        symbol="AAPL",
        quantity=10,
        side="buy",
    )

    result = executor.execute(request)

    assert result.risk_decision.status == RISK_KILL_SWITCH_TRIGGERED
    assert "Kill-switch active" in result.reason


def test_kill_switch_all_disabled_no_trigger() -> None:
    """Test no trigger when all disabled."""
    config = KillSwitchConfig()
    ks = KillSwitch(config)

    result = ks.evaluate(
        KillSwitchMetrics(
            drawdown=0.5,
            daily_loss=10000,
            rolling_sharpe=-5.0,
            consecutive_losses=10,
        )
    )

    assert result is False
    assert ks.is_active() is False