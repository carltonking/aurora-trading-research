"""Risk model dataclasses and constants."""

from dataclasses import asdict, dataclass

RISK_APPROVED = "APPROVED"
RISK_REJECTED = "REJECTED"
RISK_REDUCED_SIZE = "REDUCED_SIZE"
RISK_KILL_SWITCH_TRIGGERED = "KILL_SWITCH_TRIGGERED"


@dataclass(frozen=True)
class RiskConfig:
    """Hard risk limits for candidate evaluation."""

    max_position_pct: float = 0.05
    max_total_exposure_pct: float = 0.30
    max_daily_loss_pct: float = 0.02
    max_weekly_loss_pct: float = 0.05
    max_open_positions: int = 5
    max_trades_per_day: int = 10
    allow_shorting: bool = False
    allow_margin: bool = False
    allow_options: bool = False
    allow_crypto: bool = False
    trade_cooldown_minutes: int = 0
    kill_switch_enabled: bool = False


@dataclass(frozen=True)
class PortfolioState:
    """Portfolio state used for risk evaluation."""

    equity: float
    cash: float
    market_value: float = 0.0
    daily_pnl: float = 0.0
    weekly_pnl: float = 0.0
    open_positions: dict[str, float] | None = None
    trades_today: int = 0
    last_trade_timestamps: dict[str, str] | None = None


@dataclass(frozen=True)
class TradeCandidate:
    """Proposed trade candidate for risk review."""

    symbol: str
    side: str
    quantity: float
    price: float
    asset_class: str = "equity"
    strategy_id: str | None = None
    timestamp: str | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class RiskDecision:
    """Risk manager decision for a trade candidate."""

    status: str
    approved: bool
    original_quantity: float
    final_quantity: float
    reasons: list[str]
    candidate: TradeCandidate


def risk_decision_to_dict(decision: RiskDecision) -> dict:
    """Convert a risk decision to a dictionary."""
    return asdict(decision)
