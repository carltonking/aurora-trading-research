"""Strategy package."""

from aurora.strategies.base import SignalResult, Strategy, StrategyConfig, StrategyMetadata
from aurora.strategies.config import (
    load_strategy_config,
    strategy_config_from_dict,
    validate_strategy_config,
)
from aurora.strategies.ml_signal import MLSignalStrategy
from aurora.strategies.prompt_lab import (
    PromptLabResult,
    explain_prompt_lab_result,
    generate_strategy_config_from_prompt,
    prompt_lab_result_to_dict,
)
from aurora.strategies.registry import (
    instantiate_strategy,
    list_strategies,
    load_strategy_from_registry,
    save_strategy_config,
)
from aurora.strategies.rule_based import MomentumStrategy, MovingAverageCrossoverStrategy
from aurora.strategies.signals import (
    SIGNAL_COLUMN,
    SIGNAL_FLAT,
    SIGNAL_LONG,
    SIGNAL_REASON_COLUMN,
    empty_signal_frame,
    summarize_signals,
)

__all__ = [
    "MLSignalStrategy",
    "MomentumStrategy",
    "MovingAverageCrossoverStrategy",
    "PromptLabResult",
    "SIGNAL_COLUMN",
    "SIGNAL_FLAT",
    "SIGNAL_LONG",
    "SIGNAL_REASON_COLUMN",
    "SignalResult",
    "Strategy",
    "StrategyConfig",
    "StrategyMetadata",
    "empty_signal_frame",
    "explain_prompt_lab_result",
    "generate_strategy_config_from_prompt",
    "instantiate_strategy",
    "list_strategies",
    "load_strategy_config",
    "load_strategy_from_registry",
    "save_strategy_config",
    "prompt_lab_result_to_dict",
    "strategy_config_from_dict",
    "summarize_signals",
    "validate_strategy_config",
]
