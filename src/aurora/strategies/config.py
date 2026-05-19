"""Strategy configuration loading and validation."""

from pathlib import Path
from typing import Any

import yaml

from aurora.strategies.base import StrategyConfig
from aurora.strategies.exceptions import StrategyConfigError

ALLOWED_STRATEGY_TYPES = [
    "ml_signal",
    "momentum",
    "mean_reversion",
    "breakout",
    "moving_average_crossover",
]
ALLOWED_DIRECTIONS = ["long_only", "flat_only"]
REQUIRED_CONFIG_KEYS = [
    "strategy_id",
    "name",
    "strategy_type",
    "asset_class",
    "universe",
    "timeframe",
    "direction",
    "entry_rules",
    "exit_rules",
    "risk",
    "validation",
]


def load_strategy_config(path: str | Path) -> StrategyConfig:
    """Load and validate a strategy config from YAML."""
    config_path = Path(path)
    if not config_path.exists():
        raise StrategyConfigError(f"Strategy config not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    if not isinstance(data, dict):
        raise StrategyConfigError("Strategy config YAML must contain a mapping.")
    return strategy_config_from_dict(data)


def strategy_config_from_dict(data: dict[str, Any]) -> StrategyConfig:
    """Create a validated StrategyConfig from a dictionary."""
    missing = [key for key in REQUIRED_CONFIG_KEYS if key not in data]
    if missing:
        raise StrategyConfigError(f"Missing required strategy config keys: {', '.join(missing)}")

    config = StrategyConfig(
        strategy_id=str(data["strategy_id"]),
        name=str(data["name"]),
        strategy_type=str(data["strategy_type"]),
        asset_class=str(data["asset_class"]),
        universe=dict(data["universe"] or {}),
        timeframe=str(data["timeframe"]),
        direction=str(data["direction"]),
        entry_rules=list(data["entry_rules"] or []),
        exit_rules=list(data["exit_rules"] or []),
        risk=dict(data["risk"] or {}),
        validation=dict(data["validation"] or {}),
        metadata=dict(data["metadata"]) if data.get("metadata") is not None else None,
    )
    validate_strategy_config(config)
    return config


def validate_strategy_config(config: StrategyConfig) -> None:
    """Validate v1 strategy safety and schema rules."""
    if not config.strategy_id.strip():
        raise StrategyConfigError("strategy_id must be non-empty.")
    if config.strategy_type not in ALLOWED_STRATEGY_TYPES:
        raise StrategyConfigError(f"Unsupported strategy_type: {config.strategy_type}")
    if config.direction not in ALLOWED_DIRECTIONS:
        raise StrategyConfigError(f"Unsupported direction: {config.direction}")
    if config.asset_class not in {"equity", "etf"}:
        raise StrategyConfigError("asset_class must be equity or etf in v1.")
    if config.direction != "long_only" and config.direction != "flat_only":
        raise StrategyConfigError("Strategies may not allow shorting in v1.")

    if config.risk.get("allow_shorting") is True:
        raise StrategyConfigError("risk.allow_shorting must be false in v1.")
    if config.risk.get("allow_margin") is True:
        raise StrategyConfigError("risk.allow_margin must be false in v1.")
    if float(config.risk.get("max_position_pct", 0.0)) > 0.10:
        raise StrategyConfigError("risk.max_position_pct must be <= 0.10 in v1.")

    if not isinstance(config.universe, dict):
        raise StrategyConfigError("universe must be a mapping.")
    symbols = config.universe.get("symbols")
    filters = config.universe.get("filters")
    if not symbols and not filters:
        raise StrategyConfigError("universe must contain symbols or filters.")
    if symbols is not None and not isinstance(symbols, list):
        raise StrategyConfigError("universe.symbols must be a list when provided.")
