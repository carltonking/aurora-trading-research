import pytest

from aurora.risk.exceptions import RiskConfigError, RiskEvaluationError
from aurora.risk.models import (
    RISK_APPROVED,
    RISK_KILL_SWITCH_TRIGGERED,
    RISK_REDUCED_SIZE,
    RISK_REJECTED,
    PortfolioState,
    RiskConfig,
    TradeCandidate,
)
from aurora.risk.risk_manager import RiskManager


def _portfolio(**overrides) -> PortfolioState:
    values = {
        "equity": 100000.0,
        "cash": 100000.0,
        "market_value": 0.0,
        "daily_pnl": 0.0,
        "weekly_pnl": 0.0,
        "open_positions": {},
        "trades_today": 0,
        "last_trade_timestamps": {},
    }
    values.update(overrides)
    return PortfolioState(**values)


def _candidate(**overrides) -> TradeCandidate:
    values = {"symbol": "AAPL", "side": "buy", "quantity": 10.0, "price": 100.0}
    values.update(overrides)
    return TradeCandidate(**values)


def test_valid_buy_approved() -> None:
    decision = RiskManager().evaluate(_candidate(), _portfolio())

    assert decision.status == RISK_APPROVED
    assert decision.approved is True
    assert decision.final_quantity == 10.0


def test_oversized_buy_returns_reduced_size() -> None:
    decision = RiskManager().evaluate(_candidate(quantity=1000.0), _portfolio())

    assert decision.status == RISK_REDUCED_SIZE
    assert decision.approved is True
    assert decision.final_quantity == pytest.approx(50.0)
    assert any("max_position_pct" in reason for reason in decision.reasons)


def test_insufficient_cash_reduces_or_rejects_size() -> None:
    reduced = RiskManager().evaluate(_candidate(quantity=10.0), _portfolio(cash=500.0))
    rejected = RiskManager().evaluate(_candidate(quantity=10.0), _portfolio(cash=0.0))

    assert reduced.status == RISK_REDUCED_SIZE
    assert reduced.final_quantity == pytest.approx(5.0)
    assert rejected.status == RISK_REJECTED
    assert rejected.approved is False


def test_kill_switch_returns_kill_switch_status() -> None:
    decision = RiskManager(RiskConfig(kill_switch_enabled=True)).evaluate(_candidate(), _portfolio())

    assert decision.status == RISK_KILL_SWITCH_TRIGGERED
    assert decision.approved is False


def test_daily_loss_limit_rejects() -> None:
    decision = RiskManager().evaluate(_candidate(), _portfolio(daily_pnl=-2500.0))

    assert decision.status == RISK_REJECTED
    assert "Daily loss" in decision.reasons[0]


def test_weekly_loss_limit_rejects() -> None:
    decision = RiskManager().evaluate(_candidate(), _portfolio(weekly_pnl=-6000.0))

    assert decision.status == RISK_REJECTED
    assert "Weekly loss" in decision.reasons[0]


def test_max_trades_per_day_rejects() -> None:
    decision = RiskManager().evaluate(_candidate(), _portfolio(trades_today=10))

    assert decision.status == RISK_REJECTED
    assert "Maximum trades per day" in decision.reasons[0]


def test_max_open_positions_rejects() -> None:
    open_positions = {f"SYM{i}": 1.0 for i in range(5)}
    decision = RiskManager().evaluate(_candidate(symbol="NEW"), _portfolio(open_positions=open_positions))

    assert decision.status == RISK_REJECTED
    assert "Maximum open positions" in decision.reasons[0]


def test_crypto_rejected_by_default() -> None:
    decision = RiskManager().evaluate(_candidate(asset_class="crypto"), _portfolio())

    assert decision.status == RISK_REJECTED
    assert "Crypto" in decision.reasons[0]


def test_option_rejected_by_default() -> None:
    decision = RiskManager().evaluate(_candidate(asset_class="option"), _portfolio())

    assert decision.status == RISK_REJECTED
    assert "Option" in decision.reasons[0]


def test_sell_approved_only_if_enough_existing_quantity() -> None:
    approved = RiskManager().evaluate(
        _candidate(side="sell", quantity=5.0),
        _portfolio(open_positions={"AAPL": 10.0}),
    )
    rejected = RiskManager().evaluate(
        _candidate(side="sell", quantity=15.0),
        _portfolio(open_positions={"AAPL": 10.0}),
    )

    assert approved.status == RISK_APPROVED
    assert rejected.status == RISK_REJECTED


def test_sell_rejected_if_it_would_short() -> None:
    decision = RiskManager().evaluate(
        _candidate(side="sell", quantity=1.0),
        _portfolio(open_positions={}),
    )

    assert decision.status == RISK_REJECTED
    assert "shorting is not allowed" in decision.reasons[0]


def test_invalid_config_raises_risk_config_error() -> None:
    with pytest.raises(RiskConfigError):
        RiskManager(RiskConfig(max_position_pct=0.0))


def test_malformed_candidate_raises_risk_evaluation_error() -> None:
    with pytest.raises(RiskEvaluationError):
        RiskManager().evaluate(_candidate(quantity=0.0), _portfolio())

    with pytest.raises(RiskEvaluationError):
        RiskManager().evaluate(_candidate(side="hold"), _portfolio())


def test_trade_cooldown_rejects_when_within_cooldown() -> None:
    manager = RiskManager(RiskConfig(trade_cooldown_minutes=60))
    decision = manager.evaluate(
        _candidate(timestamp="2024-01-01T10:30:00"),
        _portfolio(last_trade_timestamps={"AAPL": "2024-01-01T10:00:00"}),
    )

    assert decision.status == RISK_REJECTED
    assert "cooldown" in decision.reasons[0]
