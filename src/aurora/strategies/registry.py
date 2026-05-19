"""Local filesystem strategy registry."""

from dataclasses import asdict
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

import yaml

from aurora.strategies.base import Strategy, StrategyConfig, StrategyMetadata
from aurora.strategies.config import validate_strategy_config
from aurora.strategies.exceptions import StrategyRegistryError
from aurora.strategies.ml_signal import MLSignalStrategy
from aurora.strategies.rule_based import MomentumStrategy, MovingAverageCrossoverStrategy


def get_strategy_registry_dir(base_dir: str | Path = "data/strategies") -> Path:
    """Return the local strategy registry directory, creating it if needed."""
    path = Path(base_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_strategy_config(
    config: StrategyConfig,
    base_dir: str | Path = "data/strategies",
) -> Path:
    """Save a validated strategy config to the local registry."""
    validate_strategy_config(config)
    registry_dir = get_strategy_registry_dir(base_dir)
    strategy_dir = registry_dir / config.strategy_id
    strategy_dir.mkdir(parents=True, exist_ok=True)

    config_path = strategy_dir / "config.yaml"
    with config_path.open("w", encoding="utf-8") as file:
        yaml.safe_dump(asdict(config), file, sort_keys=False)

    metadata = _metadata_for_config(config)
    with (strategy_dir / "metadata.json").open("w", encoding="utf-8") as file:
        json.dump(metadata, file, indent=2, sort_keys=True)

    return strategy_dir


def load_strategy_from_registry(
    strategy_id: str,
    base_dir: str | Path = "data/strategies",
) -> StrategyConfig:
    """Load a saved strategy config from the local registry."""
    config_path = Path(base_dir) / strategy_id / "config.yaml"
    if not config_path.exists():
        raise StrategyRegistryError(f"Strategy not found: {strategy_id}")
    from aurora.strategies.config import load_strategy_config

    return load_strategy_config(config_path)


def list_strategies(base_dir: str | Path = "data/strategies") -> list[dict[str, Any]]:
    """List saved strategy metadata."""
    registry_dir = Path(base_dir)
    if not registry_dir.exists():
        return []

    metadata_items = []
    for metadata_path in registry_dir.glob("*/metadata.json"):
        try:
            with metadata_path.open("r", encoding="utf-8") as file:
                metadata_items.append(json.load(file))
        except json.JSONDecodeError as exc:
            raise StrategyRegistryError(f"Invalid strategy metadata: {metadata_path}") from exc
    return sorted(metadata_items, key=lambda item: item.get("created_at", ""), reverse=True)


def instantiate_strategy(config: StrategyConfig) -> Strategy:
    """Instantiate a strategy implementation from config."""
    validate_strategy_config(config)
    if config.strategy_type == "ml_signal":
        return MLSignalStrategy(config)
    if config.strategy_type == "moving_average_crossover":
        return MovingAverageCrossoverStrategy(config)
    if config.strategy_type == "momentum":
        return MomentumStrategy(config)
    raise StrategyRegistryError(f"Strategy type is allowed but not implemented yet: {config.strategy_type}")


def _metadata_for_config(config: StrategyConfig) -> dict[str, Any]:
    metadata = dict(config.metadata or {})
    metadata.setdefault("created_at", datetime.now(UTC).isoformat())
    metadata.setdefault("status", "draft")
    metadata.update(
        {
            "strategy_id": config.strategy_id,
            "name": config.name,
            "strategy_type": config.strategy_type,
            "asset_class": config.asset_class,
            "timeframe": config.timeframe,
            "direction": config.direction,
        }
    )
    return metadata


class StrategyRegistry:
    """Compatibility in-memory strategy registry."""

    def __init__(self) -> None:
        self._strategies: dict[str, StrategyMetadata] = {}

    def register(self, metadata: StrategyMetadata) -> None:
        """Register strategy metadata."""
        self._strategies[metadata.strategy_id] = metadata

    def list_strategies(self) -> list[str]:
        """Return registered strategy identifiers."""
        return sorted(self._strategies)
