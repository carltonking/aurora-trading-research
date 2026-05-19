"""Scenario-based stress testing for strategies.

This module provides research-only stress testing to assess strategy
performance under adverse market conditions. No live trading, no broker calls.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import numpy as np


@dataclass
class ScenarioEvent:
    """A single market event in a stress scenario."""

    start_date: str
    end_date: str
    price_multiplier: float = 1.0
    volatility_multiplier: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_date": self.start_date,
            "end_date": self.end_date,
            "price_multiplier": self.price_multiplier,
            "volatility_multiplier": self.volatility_multiplier,
        }


@dataclass
class Scenario:
    """A stress test scenario with market events."""

    name: str
    description: str
    events: list[ScenarioEvent] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "events": [e.to_dict() for e in self.events],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Scenario":
        events = [ScenarioEvent(**e) for e in data.get("events", [])]
        return cls(
            name=data["name"],
            description=data["description"],
            events=events,
        )


@dataclass
class StressTestResult:
    """Result of stress test on a scenario."""

    strategy_name: str
    scenario_name: str
    original_metrics: dict[str, float] = field(default_factory=dict)
    stressed_metrics: dict[str, float] = field(default_factory=dict)
    trades: list[dict[str, Any]] = field(default_factory=list)
    scenario_description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_name": self.strategy_name,
            "scenario_name": self.scenario_name,
            "original_metrics": self.original_metrics,
            "stressed_metrics": self.stressed_metrics,
            "trades": self.trades,
            "scenario_description": self.scenario_description,
        }


BUILT_IN_SCENARIOS: dict[str, Scenario] = {
    "2008_financial_crisis": Scenario(
        name="2008 Financial Crisis",
        description="Simulate severe market crash similar to 2008 financial crisis with ~40% price decline over 6 months and elevated volatility.",
        events=[
            ScenarioEvent(
                start_date="2020-01-01",
                end_date="2020-06-30",
                price_multiplier=0.6,
                volatility_multiplier=3.0,
            )
        ],
    ),
    "2020_covid_crash": Scenario(
        name="2020 COVID Crash",
        description="Simulate rapid market crash similar to March 2020 with ~35% decline over 2 months and very high volatility.",
        events=[
            ScenarioEvent(
                start_date="2020-01-01",
                end_date="2020-02-29",
                price_multiplier=0.65,
                volatility_multiplier=4.0,
            )
        ],
    ),
    "interest_rate_spike": Scenario(
        name="Interest Rate Spike",
        description="Simulate impact of interest rate spike causing gradual 10% decline over 3 months with moderate volatility increase.",
        events=[
            ScenarioEvent(
                start_date="2020-01-01",
                end_date="2020-03-31",
                price_multiplier=0.9,
                volatility_multiplier=1.5,
            )
        ],
    ),
    "bull_market_meltdown": Scenario(
        name="Bull Market Meltdown",
        description="Simulate sudden reversal in bull market with 15% decline over 1 month and doubled volatility.",
        events=[
            ScenarioEvent(
                start_date="2020-01-01",
                end_date="2020-01-31",
                price_multiplier=0.85,
                volatility_multiplier=2.0,
            )
        ],
    ),
}


class StressTester:
    """Stress tester for strategies under adverse market scenarios.

    This is a research-only tester. It applies scenario shocks to market
    data and evaluates strategy performance. No live trading, no broker calls.
    """

    def __init__(self, strategy_fn: Callable[[pd.DataFrame], pd.Series]) -> None:
        """Initialize stress tester.

        Args:
            strategy_fn: Function that takes OHLCV DataFrame and returns signals (1 for long, 0 for flat).
        """
        self.strategy_fn = strategy_fn

    def _apply_scenario(self, data: pd.DataFrame, scenario: Scenario) -> pd.DataFrame:
        """Apply scenario events to data."""
        stressed = data.copy()

        for event in scenario.events:
            try:
                start = pd.to_datetime(event.start_date)
                end = pd.to_datetime(event.end_date)
            except Exception:
                continue

            mask = (stressed.index >= start) & (stressed.index <= end)
            if not mask.any():
                continue

            for col in ["open", "high", "low", "close", "adjusted_close"]:
                if col in stressed.columns:
                    stressed.loc[mask, col] = stressed.loc[mask, col] * event.price_multiplier

            if event.volatility_multiplier != 1.0:
                if "high" in stressed.columns and "low" in stressed.columns:
                    mid = (stressed["high"] + stressed["low"]) / 2
                    high_dist = stressed["high"] - mid
                    low_dist = mid - stressed["low"]
                    stressed.loc[mask, "high"] = mid + high_dist * event.volatility_multiplier
                    stressed.loc[mask, "low"] = mid - low_dist * event.volatility_multiplier

                if "open" in stressed.columns and "close" in stressed.columns:
                    daily_range = (stressed["high"] - stressed["low"]).abs()
                    random_noise = np.random.uniform(-1, 1, size=len(stressed))
                    stressed.loc[mask, "close"] = stressed.loc[mask, "open"] + random_noise * daily_range * event.volatility_multiplier * 0.5

        stressed["close"] = stressed["close"].clip(lower=0.01)
        stressed["high"] = stressed[["high", "close"]].max(axis=1)
        stressed["low"] = stressed[["low", "close"]].min(axis=1)

        return stressed

    def _run_simple_backtest(self, data: pd.DataFrame, signals: pd.Series) -> tuple[list[dict], dict[str, float]]:
        """Run simplified backtest on data with signals."""
        if len(signals) != len(data):
            signals = signals.reindex(data.index, method="ffill")
            signals = signals.fillna(0)

        trades = []
        position = 0
        entry_price = 0.0
        entry_idx = None

        for i, (date, row) in enumerate(data.iterrows()):
            current_signal = signals.iloc[i] if i < len(signals) else 0

            if position == 0 and current_signal == 1:
                position = 1
                entry_price = row["close"]
                entry_idx = date

            elif position == 1 and current_signal == 0:
                exit_price = row["close"]
                pnl = exit_price - entry_price
                return_pct = (exit_price - entry_price) / entry_price if entry_price > 0 else 0

                trades.append({
                    "entry_date": str(entry_idx),
                    "exit_date": str(date),
                    "entry_price": float(entry_price),
                    "exit_price": float(exit_price),
                    "pnl": float(pnl),
                    "return_pct": float(return_pct),
                })

                position = 0
                entry_price = 0.0
                entry_idx = None

        if position == 1 and data.index[-1] is not None:
            exit_price = data.iloc[-1]["close"]
            pnl = exit_price - entry_price
            return_pct = (exit_price - entry_price) / entry_price if entry_price > 0 else 0

            trades.append({
                "entry_date": str(entry_idx),
                "exit_date": str(data.index[-1]),
                "entry_price": float(entry_price),
                "exit_price": float(exit_price),
                "pnl": float(pnl),
                "return_pct": float(return_pct),
            })

        return trades, self._compute_metrics(trades, data)

    def _compute_metrics(self, trades: list[dict], data: pd.DataFrame) -> dict[str, float]:
        """Compute metrics from trades."""
        if not trades:
            return {
                "total_return": 0.0,
                "max_drawdown": 0.0,
                "win_rate": 0.0,
                "sharpe_ratio": 0.0,
                "trade_count": 0,
            }

        pnls = [t["pnl"] for t in trades]

        total_return = sum(pnls)
        wins = sum(1 for p in pnls if p > 0)
        win_rate = wins / len(pnls) if pnls else 0.0

        equity = [0]
        for pnl in pnls:
            equity.append(equity[-1] + pnl)

        peak = equity[0]
        max_dd = 0.0
        for eq in equity:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / max(peak, 1) if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd

        daily_returns = [t["return_pct"] for t in trades]
        mean_return = np.mean(daily_returns) if daily_returns else 0.0
        std_return = np.std(daily_returns, ddof=1) if len(daily_returns) > 1 else 0.0
        sharpe = (mean_return / std_return * np.sqrt(252)) if std_return > 0 else 0.0

        return {
            "total_return": float(total_return),
            "max_drawdown": float(max_dd),
            "win_rate": float(win_rate),
            "sharpe_ratio": float(sharpe),
            "trade_count": len(trades),
        }

    def run_scenario(self, base_data: pd.DataFrame, scenario: Scenario, strategy_name: str = "strategy") -> StressTestResult:
        """Run stress test on a scenario.

        Args:
            base_data: Original OHLCV DataFrame.
            scenario: Scenario to apply.
            strategy_name: Name of the strategy.

        Returns:
            StressTestResult with original and stressed metrics.
        """
        original_signals = self.strategy_fn(base_data)
        original_trades, original_metrics = self._run_simple_backtest(base_data, original_signals)

        stressed_data = self._apply_scenario(base_data, scenario)
        stressed_signals = self.strategy_fn(stressed_data)
        stressed_trades, stressed_metrics = self._run_simple_backtest(stressed_data, stressed_signals)

        return StressTestResult(
            strategy_name=strategy_name,
            scenario_name=scenario.name,
            original_metrics=original_metrics,
            stressed_metrics=stressed_metrics,
            trades=stressed_trades,
            scenario_description=scenario.description,
        )

    def run_all_scenarios(self, base_data: pd.DataFrame, scenario_names: list[str] | None = None) -> list[StressTestResult]:
        """Run stress test on all built-in scenarios.

        Args:
            base_data: Original OHLCV DataFrame.
            scenario_names: Optional list of scenario names to run. If None, runs all.

        Returns:
            List of StressTestResult for each scenario.
        """
        if scenario_names is None:
            scenario_names = list(BUILT_IN_SCENARIOS.keys())

        results = []
        for name in scenario_names:
            if name in BUILT_IN_SCENARIOS:
                scenario = BUILT_IN_SCENARIOS[name]
                result = self.run_scenario(base_data, scenario)
                results.append(result)

        return results

    def save_result(self, result: StressTestResult, output_path: str) -> Path:
        """Save stress test result to JSON."""
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with output_file.open("w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2, sort_keys=False)

        return output_file

    def save_results(self, results: list[StressTestResult], output_path: str) -> Path:
        """Save multiple stress test results to JSON."""
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        data = {"results": [r.to_dict() for r in results]}

        with output_file.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=False)

        return output_file


def load_scenario(path: str) -> Scenario:
    """Load scenario from JSON file."""
    with Path(path).open() as f:
        data = json.load(f)
    return Scenario.from_dict(data)


def list_built_in_scenarios() -> dict[str, str]:
    """List available built-in scenarios."""
    return {name: scenario.description for name, scenario in BUILT_IN_SCENARIOS.items()}