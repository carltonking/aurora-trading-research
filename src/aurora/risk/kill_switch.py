"""Kill-switch system for paper trading risk controls."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class KillSwitchState(Enum):
    """Kill-switch state."""

    ACTIVE = "ACTIVE"
    KILLED = "KILLED"


@dataclass
class KillSwitchConfig:
    """Configuration for kill-switch triggers.

    All fields are optional - None means the trigger is disabled.
    """

    max_portfolio_drawdown: Optional[float] = None
    max_daily_loss: Optional[float] = None
    min_sharpe: Optional[float] = None
    max_consecutive_losses: Optional[int] = None
    emergency_kill: bool = False


@dataclass
class KillSwitchMetrics:
    """Portfolio metrics for kill-switch evaluation."""

    drawdown: float = 0.0
    daily_loss: float = 0.0
    rolling_sharpe: float = 0.0
    consecutive_losses: int = 0
    peak_equity: float = 0.0
    current_equity: float = 0.0


class KillSwitch:
    """Kill-switch that halts paper order submissions when thresholds breach."""

    def __init__(self, config: KillSwitchConfig) -> None:
        self._config = config
        self._state = KillSwitchState.ACTIVE
        self._trigger_reason: Optional[str] = None

    def evaluate(self, metrics: KillSwitchMetrics) -> bool:
        """Evaluate kill-switch conditions.

        Args:
            metrics: Portfolio metrics dictionary with keys:
                - drawdown: current drawdown from peak (0.0-1.0)
                - daily_loss: realized daily loss in dollars
                - rolling_sharpe: rolling Sharpe ratio
                - consecutive_losses: number of consecutive losing trades
                - peak_equity: peak portfolio equity
                - current_equity: current portfolio equity

        Returns:
            True if any condition is met (kill-switch should activate).
        """
        if self._state == KillSwitchState.KILLED:
            return True

        reasons = []

        if self._config.max_portfolio_drawdown is not None:
            if metrics.drawdown >= self._config.max_portfolio_drawdown:
                reasons.append(
                    f"max_drawdown={metrics.drawdown:.2%} >= {self._config.max_portfolio_drawdown:.2%}"
                )

        if self._config.max_daily_loss is not None:
            if metrics.daily_loss >= self._config.max_daily_loss:
                reasons.append(
                    f"daily_loss=${metrics.daily_loss:.2f} >= ${self._config.max_daily_loss:.2f}"
                )

        if self._config.min_sharpe is not None:
            if metrics.rolling_sharpe < self._config.min_sharpe:
                reasons.append(
                    f"sharpe={metrics.rolling_sharpe:.2f} < {self._config.min_sharpe:.2f}"
                )

        if self._config.max_consecutive_losses is not None:
            if metrics.consecutive_losses >= self._config.max_consecutive_losses:
                reasons.append(
                    f"consecutive_losses={metrics.consecutive_losses} >= {self._config.max_consecutive_losses}"
                )

        if self._config.emergency_kill:
            reasons.append("emergency_kill=true")

        if reasons:
            self._trigger_reason = "; ".join(reasons)
            return True

        return False

    def activate(self, reason: Optional[str] = None) -> None:
        """Manually activate kill-switch."""
        self._state = KillSwitchState.KILLED
        self._trigger_reason = reason or "manual_activation"

    def deactivate(self) -> None:
        """Manually deactivate kill-switch."""
        self._state = KillSwitchState.ACTIVE
        self._trigger_reason = None

    def is_active(self) -> bool:
        """Check if kill-switch is active (killed)."""
        return self._state == KillSwitchState.KILLED

    @property
    def trigger_reason(self) -> Optional[str]:
        """Get the reason why kill-switch was activated."""
        return self._trigger_reason


def get_kill_switch_config_from_env() -> KillSwitchConfig:
    """Create KillSwitchConfig from environment variables."""
    import os

    max_dd = os.getenv("AURORA_KS_MAX_DRAWDOWN")
    max_dl = os.getenv("AURORA_KS_MAX_DAILY_LOSS")
    min_sharpe = os.getenv("AURORA_KS_MIN_SHARPE")
    max_losses = os.getenv("AURORA_KS_MAX_CONSECUTIVE_LOSSES")
    emergency = os.getenv("AURORA_KS_EMERGENCY_KILL", "false").lower() == "true"

    return KillSwitchConfig(
        max_portfolio_drawdown=float(max_dd) if max_dd else None,
        max_daily_loss=float(max_dl) if max_dl else None,
        min_sharpe=float(min_sharpe) if min_sharpe else None,
        max_consecutive_losses=int(max_losses) if max_losses else None,
        emergency_kill=emergency,
    )