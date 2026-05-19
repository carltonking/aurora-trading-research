"""Deterministic hard-gate risk manager."""

from dataclasses import fields
from datetime import datetime

from aurora.risk.exceptions import RiskConfigError, RiskEvaluationError
from aurora.risk.models import (
    RISK_APPROVED,
    RISK_KILL_SWITCH_TRIGGERED,
    RISK_REDUCED_SIZE,
    RISK_REJECTED,
    PortfolioState,
    RiskConfig,
    RiskDecision,
    TradeCandidate,
)


class RiskManager:
    """Evaluate proposed trade candidates against hard risk limits."""

    def __init__(self, config: RiskConfig | dict | None = None) -> None:
        self.config = self._coerce_config(config)
        self.validate_config()

    def evaluate(self, candidate: TradeCandidate, portfolio: PortfolioState) -> RiskDecision:
        """Evaluate a trade candidate against configured hard limits."""
        self._validate_candidate(candidate)
        if portfolio.equity <= 0:
            raise RiskEvaluationError("portfolio.equity must be greater than 0.")
        if portfolio.cash < 0:
            raise RiskEvaluationError("portfolio.cash cannot be negative.")

        if self.config.kill_switch_enabled:
            return self.kill_switch_decision(candidate)

        if candidate.side == "sell":
            return self._evaluate_sell(candidate, portfolio)

        return self._evaluate_buy(candidate, portfolio)

    def validate_config(self) -> None:
        """Validate risk configuration bounds."""
        if not 0 < self.config.max_position_pct <= 1:
            raise RiskConfigError("max_position_pct must be > 0 and <= 1.")
        if not 0 < self.config.max_total_exposure_pct <= 1:
            raise RiskConfigError("max_total_exposure_pct must be > 0 and <= 1.")
        if not 0 < self.config.max_daily_loss_pct <= 1:
            raise RiskConfigError("max_daily_loss_pct must be > 0 and <= 1.")
        if not 0 < self.config.max_weekly_loss_pct <= 1:
            raise RiskConfigError("max_weekly_loss_pct must be > 0 and <= 1.")
        if self.config.max_open_positions < 0:
            raise RiskConfigError("max_open_positions must be >= 0.")
        if self.config.max_trades_per_day < 0:
            raise RiskConfigError("max_trades_per_day must be >= 0.")
        if self.config.trade_cooldown_minutes < 0:
            raise RiskConfigError("trade_cooldown_minutes must be >= 0.")

    def kill_switch_decision(self, candidate: TradeCandidate) -> RiskDecision:
        """Return a kill-switch rejection decision."""
        return RiskDecision(
            status=RISK_KILL_SWITCH_TRIGGERED,
            approved=False,
            original_quantity=candidate.quantity,
            final_quantity=0.0,
            reasons=["Kill switch is enabled."],
            candidate=candidate,
        )

    def describe(self) -> str:
        """Return a short description of the component."""
        return "Evaluates trade candidates against hard research risk limits."

    def _evaluate_sell(self, candidate: TradeCandidate, portfolio: PortfolioState) -> RiskDecision:
        open_positions = portfolio.open_positions or {}
        current_quantity = float(open_positions.get(candidate.symbol, 0.0))
        if current_quantity < candidate.quantity:
            return self._reject(
                candidate,
                f"Sell quantity {candidate.quantity} exceeds open quantity {current_quantity}; shorting is not allowed.",
            )
        return self._approve(candidate, candidate.quantity, ["Sell is covered by existing position."])

    def _evaluate_buy(self, candidate: TradeCandidate, portfolio: PortfolioState) -> RiskDecision:
        hard_reject = self._hard_reject_reason(candidate, portfolio)
        if hard_reject is not None:
            return self._reject(candidate, hard_reject)

        reasons: list[str] = []
        final_quantity = candidate.quantity
        final_quantity = self._cap_by_position_limit(candidate, portfolio, final_quantity, reasons)
        final_quantity = self._cap_by_total_exposure(candidate, portfolio, final_quantity, reasons)
        final_quantity = self._cap_by_cash(candidate, portfolio, final_quantity, reasons)

        if final_quantity <= 0:
            return self._reject(candidate, "No allowable quantity remains after risk limits.")

        if final_quantity < candidate.quantity:
            return RiskDecision(
                status=RISK_REDUCED_SIZE,
                approved=True,
                original_quantity=candidate.quantity,
                final_quantity=final_quantity,
                reasons=reasons or ["Quantity reduced by risk limits."],
                candidate=candidate,
            )

        return self._approve(candidate, final_quantity, reasons or ["Trade candidate approved."])

    def _hard_reject_reason(
        self,
        candidate: TradeCandidate,
        portfolio: PortfolioState,
    ) -> str | None:
        if candidate.asset_class == "crypto" and not self.config.allow_crypto:
            return "Crypto candidates are not allowed by risk configuration."
        if candidate.asset_class == "option" and not self.config.allow_options:
            return "Option candidates are not allowed by risk configuration."
        if self.config.max_trades_per_day == 0 or portfolio.trades_today >= self.config.max_trades_per_day:
            return "Maximum trades per day has been reached."
        if portfolio.daily_pnl / portfolio.equity <= -self.config.max_daily_loss_pct:
            return "Daily loss limit has been reached."
        if portfolio.weekly_pnl / portfolio.equity <= -self.config.max_weekly_loss_pct:
            return "Weekly loss limit has been reached."
        if self._would_exceed_open_position_count(candidate, portfolio):
            return "Maximum open positions limit has been reached."
        if self._within_cooldown(candidate, portfolio):
            return "Trade cooldown is still active for this symbol."
        return None

    def _cap_by_position_limit(
        self,
        candidate: TradeCandidate,
        portfolio: PortfolioState,
        quantity: float,
        reasons: list[str],
    ) -> float:
        open_positions = portfolio.open_positions or {}
        existing_quantity = float(open_positions.get(candidate.symbol, 0.0))
        max_position_value = self.config.max_position_pct * portfolio.equity
        available_position_value = max_position_value - (existing_quantity * candidate.price)
        allowed_quantity = available_position_value / candidate.price
        capped_quantity = min(quantity, allowed_quantity)
        if capped_quantity < quantity:
            reasons.append("Quantity reduced to respect max_position_pct.")
        return max(0.0, capped_quantity)

    def _cap_by_total_exposure(
        self,
        candidate: TradeCandidate,
        portfolio: PortfolioState,
        quantity: float,
        reasons: list[str],
    ) -> float:
        max_exposure_value = self.config.max_total_exposure_pct * portfolio.equity
        available_exposure_value = max_exposure_value - portfolio.market_value
        allowed_quantity = available_exposure_value / candidate.price
        capped_quantity = min(quantity, allowed_quantity)
        if capped_quantity < quantity:
            reasons.append("Quantity reduced to respect max_total_exposure_pct.")
        return max(0.0, capped_quantity)

    def _cap_by_cash(
        self,
        candidate: TradeCandidate,
        portfolio: PortfolioState,
        quantity: float,
        reasons: list[str],
    ) -> float:
        if self.config.allow_margin:
            return quantity
        allowed_quantity = portfolio.cash / candidate.price
        capped_quantity = min(quantity, allowed_quantity)
        if capped_quantity < quantity:
            reasons.append("Quantity reduced to available cash; margin is disabled.")
        return max(0.0, capped_quantity)

    def _would_exceed_open_position_count(
        self,
        candidate: TradeCandidate,
        portfolio: PortfolioState,
    ) -> bool:
        open_positions = portfolio.open_positions or {}
        if candidate.symbol in open_positions:
            return False
        return len(open_positions) >= self.config.max_open_positions

    def _within_cooldown(self, candidate: TradeCandidate, portfolio: PortfolioState) -> bool:
        if self.config.trade_cooldown_minutes <= 0 or not candidate.timestamp:
            return False
        last_timestamps = portfolio.last_trade_timestamps or {}
        last_timestamp = last_timestamps.get(candidate.symbol)
        if not last_timestamp:
            return False
        current = self._parse_timestamp(candidate.timestamp)
        previous = self._parse_timestamp(last_timestamp)
        elapsed_minutes = (current - previous).total_seconds() / 60
        return elapsed_minutes < self.config.trade_cooldown_minutes

    def _validate_candidate(self, candidate: TradeCandidate) -> None:
        if candidate.quantity <= 0:
            raise RiskEvaluationError("candidate.quantity must be greater than 0.")
        if candidate.price <= 0:
            raise RiskEvaluationError("candidate.price must be greater than 0.")
        if candidate.side not in {"buy", "sell"}:
            raise RiskEvaluationError("candidate.side must be buy or sell.")
        if candidate.asset_class not in {"equity", "etf", "crypto", "option"}:
            raise RiskEvaluationError("candidate.asset_class is unsupported.")

    def _approve(
        self,
        candidate: TradeCandidate,
        final_quantity: float,
        reasons: list[str],
    ) -> RiskDecision:
        return RiskDecision(
            status=RISK_APPROVED,
            approved=True,
            original_quantity=candidate.quantity,
            final_quantity=final_quantity,
            reasons=reasons,
            candidate=candidate,
        )

    def _reject(self, candidate: TradeCandidate, reason: str) -> RiskDecision:
        return RiskDecision(
            status=RISK_REJECTED,
            approved=False,
            original_quantity=candidate.quantity,
            final_quantity=0.0,
            reasons=[reason],
            candidate=candidate,
        )

    def _coerce_config(self, config: RiskConfig | dict | None) -> RiskConfig:
        if config is None:
            return RiskConfig()
        if isinstance(config, RiskConfig):
            return config
        allowed_fields = {field.name for field in fields(RiskConfig)}
        filtered = {key: value for key, value in config.items() if key in allowed_fields}
        return RiskConfig(**filtered)

    def _parse_timestamp(self, value: str) -> datetime:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise RiskEvaluationError(f"Invalid ISO timestamp: {value}") from exc
