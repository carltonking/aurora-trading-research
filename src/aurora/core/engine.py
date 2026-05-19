"""Core research engine scaffold."""

from typing import Any

from aurora.core.constants import DEFAULT_MODE, PROJECT_NAME


class AuroraEngine:
    """Minimal safe-mode engine for the initial scaffold."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.validate_safe_mode()

    @property
    def mode(self) -> str:
        """Return the configured operating mode."""
        return str(self.config.get("mode", DEFAULT_MODE))

    def validate_safe_mode(self) -> None:
        """Reject live trading mode in the research scaffold."""
        if self.mode.lower() == "live":
            raise ValueError("Live trading is not supported in AURORA v1.")

        execution = self.config.get("execution", {})
        if isinstance(execution, dict) and execution.get("live_trading_enabled") is True:
            raise ValueError("live_trading_enabled must remain false in AURORA v1.")

    def status(self) -> dict[str, Any]:
        """Return a simple engine status payload."""
        return {
            "project": PROJECT_NAME,
            "mode": self.mode,
            "live_trading_enabled": False,
        }
