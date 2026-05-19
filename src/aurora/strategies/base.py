"""Base classes and dataclasses for research strategies."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class StrategyMetadata:
    """Minimal metadata describing a strategy candidate."""

    strategy_id: str
    name: str
    strategy_type: str


@dataclass(frozen=True)
class StrategyConfig:
    """Validated research strategy configuration."""

    strategy_id: str
    name: str
    strategy_type: str
    asset_class: str
    universe: dict[str, Any]
    timeframe: str
    direction: str
    entry_rules: list[dict[str, Any]]
    exit_rules: list[dict[str, Any]]
    risk: dict[str, Any]
    validation: dict[str, Any]
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class SignalResult:
    """Summary of generated research signals."""

    strategy_id: str
    row_count: int
    signal_count: int
    long_count: int
    flat_count: int
    created_at: str


class Strategy(ABC):
    """Abstract base class for research-only signal generators."""

    def __init__(self, config: StrategyConfig) -> None:
        self.config = config

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> tuple[pd.DataFrame, SignalResult]:
        """Generate research signals from an input dataframe."""
