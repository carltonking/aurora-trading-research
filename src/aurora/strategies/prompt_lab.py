"""Deterministic rule-based strategy prompt lab."""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import re
from typing import Any

from aurora.strategies.base import StrategyConfig
from aurora.strategies.config import validate_strategy_config

DEFAULT_SYMBOLS = ["SPY", "QQQ", "DIA"]
DEFAULT_TIMEFRAME = "1d"
DEFAULT_ASSET_CLASS = "etf"
DEFAULT_MAX_POSITION_PCT = 0.05
DEFAULT_MIN_PROBABILITY = 0.55

_IGNORED_TICKERS = {
    "AI",
    "ML",
    "RSI",
    "SMA",
    "EMA",
    "ETF",
    "ETFS",
    "HFT",
    "API",
    "CEO",
    "USD",
}
_UNSUPPORTED_PATTERNS = {
    "short": "shorting",
    "shorting": "shorting",
    "short sell": "short selling",
    "margin": "margin",
    "leverage": "leverage",
    "leveraged": "leverage",
    "options": "options",
    "option": "options",
    "crypto": "crypto",
    "scalping": "scalping",
    "high frequency": "high frequency trading",
    "hft": "high frequency trading",
    "live trading": "live trading",
    "real money": "real money trading",
    "real money trading": "real money trading",
}


@dataclass(frozen=True)
class PromptLabResult:
    """Result from deterministic strategy prompt parsing."""

    prompt: str
    config: StrategyConfig
    warnings: list[str]
    unsupported_requests: list[str]
    created_at: str


def generate_strategy_config_from_prompt(
    prompt: str,
    strategy_id: str | None = None,
    name: str | None = None,
) -> PromptLabResult:
    """Generate a validated strategy config draft from a simple prompt."""
    if not prompt.strip():
        raise ValueError("prompt must be non-empty.")

    lower_prompt = prompt.lower()
    warnings: list[str] = []
    unsupported_requests = _unsupported_requests(lower_prompt)
    for request in unsupported_requests:
        warnings.append(f"Unsupported request ignored in v1: {request}.")
    _add_unsupported_strategy_requests(lower_prompt, warnings, unsupported_requests)

    strategy_type = _infer_strategy_type(lower_prompt, warnings, unsupported_requests)
    symbols = _extract_symbols(prompt)
    using_default_symbols = not symbols
    if using_default_symbols:
        symbols = list(DEFAULT_SYMBOLS)
    asset_class = DEFAULT_ASSET_CLASS if using_default_symbols or _mentions_etf(lower_prompt) else "equity"

    max_position_pct = DEFAULT_MAX_POSITION_PCT
    if _is_conservative(lower_prompt):
        max_position_pct = 0.03
    elif "aggressive" in lower_prompt:
        warnings.append("Aggressive sizing request capped at v1 default max_position_pct 0.05.")

    config = StrategyConfig(
        strategy_id=strategy_id or _default_strategy_id(prompt, strategy_type),
        name=name or _default_name(strategy_type, symbols),
        strategy_type=strategy_type,
        asset_class=asset_class,
        universe={"symbols": symbols},
        timeframe=DEFAULT_TIMEFRAME,
        direction="long_only",
        entry_rules=[_entry_rule(strategy_type, lower_prompt)],
        exit_rules=[{"max_holding_period": {"days": _holding_period_days(lower_prompt)}}],
        risk={
            "max_position_pct": max_position_pct,
            "allow_shorting": False,
            "allow_margin": False,
        },
        validation={
            "require_walk_forward": True,
            "min_trades": 50,
            "include_slippage": True,
            "include_transaction_costs": True,
        },
        metadata={
            "generated_by": "strategy_prompt_lab",
            "original_prompt": prompt,
            "parser_version": "rule_based_v1",
        },
    )
    validate_strategy_config(config)
    return PromptLabResult(
        prompt=prompt,
        config=config,
        warnings=warnings,
        unsupported_requests=unsupported_requests,
        created_at=datetime.now(UTC).isoformat(),
    )


def explain_prompt_lab_result(result: PromptLabResult) -> str:
    """Return a readable explanation of a prompt lab result."""
    config = result.config
    entry_rule = config.entry_rules[0] if config.entry_rules else {}
    lines = [
        "Prompt Lab creates strategy configs only and does not trade or place orders.",
        f"Strategy type: {config.strategy_type}",
        f"Symbols: {', '.join(config.universe.get('symbols', []))}",
        f"Timeframe: {config.timeframe}",
        f"Direction: {config.direction} (long-only posture; shorting disabled)",
        f"Main entry rule: {entry_rule}",
        f"Risk: max_position_pct={config.risk.get('max_position_pct')}, "
        f"allow_shorting={config.risk.get('allow_shorting')}, "
        f"allow_margin={config.risk.get('allow_margin')}",
    ]
    if result.unsupported_requests:
        lines.append(f"Unsupported requests: {', '.join(result.unsupported_requests)}")
    if result.warnings:
        lines.append(f"Warnings: {'; '.join(result.warnings)}")
    return "\n".join(lines)


def prompt_lab_result_to_dict(result: PromptLabResult) -> dict[str, Any]:
    """Convert a PromptLabResult to a JSON-serializable dictionary."""
    return {
        "prompt": result.prompt,
        "config": asdict(result.config),
        "warnings": list(result.warnings),
        "unsupported_requests": list(result.unsupported_requests),
        "created_at": result.created_at,
    }


def _infer_strategy_type(
    lower_prompt: str,
    warnings: list[str],
    unsupported_requests: list[str],
) -> str:
    if any(token in lower_prompt for token in ["moving average", "sma", "crossover", "ma crossover"]):
        return "moving_average_crossover"
    if "momentum" in lower_prompt:
        return "momentum"
    if (
        any(token in lower_prompt for token in ["machine learning", "prediction", "model"])
        or re.search(r"\b(ai|ml)\b", lower_prompt)
    ):
        return "ml_signal"
    if "breakout" in lower_prompt:
        return "momentum"
    if any(token in lower_prompt for token in ["mean reversion", "rsi", "bollinger"]):
        return "momentum"
    return "momentum"


def _extract_symbols(prompt: str) -> list[str]:
    tokens = re.findall(r"\b[A-Z]{1,5}\b", prompt)
    symbols = []
    for token in tokens:
        if token in _IGNORED_TICKERS or token in symbols:
            continue
        symbols.append(token)
    return symbols


def _mentions_etf(lower_prompt: str) -> bool:
    return bool(re.search(r"\betfs?\b", lower_prompt))


def _unsupported_requests(lower_prompt: str) -> list[str]:
    requests = []
    for pattern, label in _UNSUPPORTED_PATTERNS.items():
        if pattern in lower_prompt and label not in requests:
            requests.append(label)
    return requests


def _add_unsupported_strategy_requests(
    lower_prompt: str,
    warnings: list[str],
    unsupported_requests: list[str],
) -> None:
    if "breakout" in lower_prompt and "breakout strategy implementation" not in unsupported_requests:
        unsupported_requests.append("breakout strategy implementation")
        warnings.append("Breakout parsing is not implemented in v1; generated a safe supported draft.")
    if (
        any(token in lower_prompt for token in ["mean reversion", "rsi", "bollinger"])
        and "mean reversion strategy implementation" not in unsupported_requests
    ):
        unsupported_requests.append("mean reversion strategy implementation")
        warnings.append("Mean reversion parsing is not implemented in v1; generated a safe supported draft.")


def _is_conservative(lower_prompt: str) -> bool:
    return "conservative" in lower_prompt or "low risk" in lower_prompt


def _entry_rule(strategy_type: str, lower_prompt: str) -> dict[str, Any]:
    if strategy_type == "moving_average_crossover":
        if "50" in lower_prompt and "200" in lower_prompt:
            return {"fast_ma": "ma_50", "slow_ma": "ma_200"}
        return {"fast_ma": "ma_20", "slow_ma": "ma_50"}

    if strategy_type == "ml_signal":
        return {
            "prediction_col": "prediction",
            "probability_col": "prediction_probability",
            "min_probability": 0.60 if _is_conservative(lower_prompt) else DEFAULT_MIN_PROBABILITY,
        }

    return {
        "return_col": "return_5d" if _mentions_day_period(lower_prompt, 5) else "return_20d",
        "min_return": 0.05 if _is_conservative(lower_prompt) else 0.03,
    }


def _holding_period_days(lower_prompt: str) -> int:
    for days in [5, 10, 20]:
        if re.search(rf"\b{days}[- ]day hold\b", lower_prompt):
            return days
    return 20


def _mentions_day_period(lower_prompt: str, days: int) -> bool:
    return bool(re.search(rf"\b{days}[- ]day\b", lower_prompt))


def _default_strategy_id(prompt: str, strategy_type: str) -> str:
    digest = hashlib.sha256(prompt.strip().lower().encode("utf-8")).hexdigest()[:8]
    return f"{strategy_type}_{digest}"


def _default_name(strategy_type: str, symbols: list[str]) -> str:
    readable_type = strategy_type.replace("_", " ").title()
    return f"{readable_type} Draft ({', '.join(symbols)})"
