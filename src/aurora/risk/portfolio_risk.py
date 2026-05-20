"""Portfolio risk configuration and manager extension."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PortfolioRiskConfig:
    """Configuration for portfolio-level risk management."""

    max_portfolio_drawdown: float = 0.20
    max_daily_loss: float = 5000.0
    max_position_concentration: float = 0.25
    max_sector_concentration: dict[str, float] = field(default_factory=dict)
    max_correlation_exposure: float = 0.80
    max_total_exposure: float = 0.95
    kill_switch_drawdown: float = 0.30

    @classmethod
    def from_env(cls) -> "PortfolioRiskConfig":
        """Load config from environment variables."""
        return cls(
            max_portfolio_drawdown=float(os.getenv("AURORA_MAX_PORTFOLIO_DRAWDOWN", "0.20")),
            max_daily_loss=float(os.getenv("AURORA_MAX_DAILY_LOSS", "5000.0")),
            max_position_concentration=float(os.getenv("AURORA_MAX_POSITION_CONCENTRATION", "0.25")),
            max_correlation_exposure=float(os.getenv("AURORA_MAX_CORRELATION_EXPOSURE", "0.80")),
            max_total_exposure=float(os.getenv("AURORA_MAX_TOTAL_EXPOSURE", "0.95")),
            kill_switch_drawdown=float(os.getenv("AURORA_KILL_SWITCH_DRAWDOWN", "0.30")),
        )

    @classmethod
    def from_file(cls, path: Path) -> "PortfolioRiskConfig":
        """Load config from JSON file."""
        if not path.exists():
            return cls()

        with path.open() as f:
            data = json.load(f)

        return cls(
            max_portfolio_drawdown=data.get("max_portfolio_drawdown", 0.20),
            max_daily_loss=data.get("max_daily_loss", 5000.0),
            max_position_concentration=data.get("max_position_concentration", 0.25),
            max_sector_concentration=data.get("max_sector_concentration", {}),
            max_correlation_exposure=data.get("max_correlation_exposure", 0.80),
            max_total_exposure=data.get("max_total_exposure", 0.95),
            kill_switch_drawdown=data.get("kill_switch_drawdown", 0.30),
        )

    def to_file(self, path: Path) -> None:
        """Save config to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as f:
            json.dump({
                "max_portfolio_drawdown": self.max_portfolio_drawdown,
                "max_daily_loss": self.max_daily_loss,
                "max_position_concentration": self.max_position_concentration,
                "max_sector_concentration": self.max_sector_concentration,
                "max_correlation_exposure": self.max_correlation_exposure,
                "max_total_exposure": self.max_total_exposure,
                "kill_switch_drawdown": self.kill_switch_drawdown,
            }, f, indent=2)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "max_portfolio_drawdown": self.max_portfolio_drawdown,
            "max_daily_loss": self.max_daily_loss,
            "max_position_concentration": self.max_position_concentration,
            "max_sector_concentration": self.max_sector_concentration,
            "max_correlation_exposure": self.max_correlation_exposure,
            "max_total_exposure": self.max_total_exposure,
            "kill_switch_drawdown": self.kill_switch_drawdown,
        }