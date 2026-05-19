"""Sensitivity analysis for strategy parameters.

This module provides research-only sensitivity analysis to identify
fragile parameters. No live trading, no broker calls.
"""

import itertools
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd


@dataclass
class ParamRange:
    """Range for a parameter to test."""

    min_value: float | None = None
    max_value: float | None = None
    step: float | None = None
    values: list[Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "min": self.min_value,
            "max": self.max_value,
            "step": self.step,
            "values": self.values,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ParamRange":
        return cls(
            min_value=data.get("min"),
            max_value=data.get("max"),
            step=data.get("step"),
            values=data.get("values"),
        )

    def generate_values(self) -> list[Any]:
        """Generate list of values for this range."""
        if self.values is not None:
            return self.values

        if self.min_value is not None and self.max_value is not None and self.step is not None:
            values = []
            current = self.min_value
            while current <= self.max_value:
                values.append(current)
                current += self.step
            return values

        return []


@dataclass
class SensitivityConfig:
    """Configuration for sensitivity analysis."""

    parameters: dict[str, ParamRange] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SensitivityConfig":
        parameters = {}
        for param_name, param_data in data.items():
            if isinstance(param_data, dict):
                parameters[param_name] = ParamRange.from_dict(param_data)
            elif isinstance(param_data, list):
                parameters[param_name] = ParamRange(values=param_data)
        return cls(parameters=parameters)

    def to_dict(self) -> dict[str, Any]:
        return {name: param.to_dict() for name, param in self.parameters.items()}


@dataclass
class SensitivityResult:
    """Result of sensitivity analysis."""

    strategy_name: str
    metric_name: str
    base_metrics: dict[str, float] = field(default_factory=dict)
    parameter_results: list[dict[str, Any]] = field(default_factory=list)
    most_sensitive: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_name": self.strategy_name,
            "metric_name": self.metric_name,
            "base_metrics": self.base_metrics,
            "parameter_results": self.parameter_results,
            "most_sensitive": self.most_sensitive,
        }


class SensitivityAnalyzer:
    """Sensitivity analyzer for strategy parameters.

    This is a research-only analyzer. It varies strategy parameters and
    measures metric changes. No live trading, no broker calls.
    """

    def __init__(
        self,
        strategy_builder: Callable[[dict], Callable[[pd.DataFrame], pd.Series]],
        base_data: pd.DataFrame,
    ) -> None:
        """Initialize sensitivity analyzer.

        Args:
            strategy_builder: Function that takes params dict and returns a strategy function.
            base_data: OHLCV DataFrame to test on.
        """
        self.strategy_builder = strategy_builder
        self.base_data = base_data

    def _run_simple_backtest(self, strategy_fn: Callable[[pd.DataFrame], pd.Series]) -> dict[str, float]:
        """Run simplified backtest and compute metrics."""
        signals = strategy_fn(self.base_data)

        if len(signals) != len(self.base_data):
            signals = signals.reindex(self.base_data.index, method="ffill")
            signals = signals.fillna(0)

        trades = []
        position = 0
        entry_price = 0.0

        for i, (date, row) in enumerate(self.base_data.iterrows()):
            current_signal = signals.iloc[i] if i < len(signals) else 0

            if position == 0 and current_signal == 1:
                position = 1
                entry_price = row["close"]

            elif position == 1 and current_signal == 0:
                exit_price = row["close"]
                pnl = exit_price - entry_price
                trades.append(pnl)
                position = 0

        if position == 1:
            exit_price = self.base_data.iloc[-1]["close"]
            trades.append(exit_price - entry_price)

        if not trades:
            return {"sharpe_ratio": 0.0, "total_return": 0.0, "max_drawdown": 0.0, "win_rate": 0.0}

        total_return = sum(trades)
        wins = sum(1 for t in trades if t > 0)
        win_rate = wins / len(trades) if trades else 0.0

        equity = [0]
        for t in trades:
            equity.append(equity[-1] + t)

        peak = equity[0]
        max_dd = 0.0
        for eq in equity:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / max(peak, 1) if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd

        daily_returns = [t / max(abs(self.base_data.iloc[i]["close"]), 1) for i, t in enumerate(trades)]
        mean_ret = np.mean(daily_returns) if daily_returns else 0.0
        std_ret = np.std(daily_returns, ddof=1) if len(daily_returns) > 1 else 0.0
        sharpe = (mean_ret / std_ret * 14) if std_ret > 0 else 0.0

        return {
            "sharpe_ratio": float(sharpe),
            "total_return": float(total_return),
            "max_drawdown": float(max_dd),
            "win_rate": float(win_rate),
        }

    def analyze(self, config: SensitivityConfig, metric: str = "sharpe_ratio") -> SensitivityResult:
        """Run sensitivity analysis.

        Args:
            config: Sensitivity configuration.
            metric: Metric to analyze (default: sharpe_ratio).

        Returns:
            SensitivityResult with analysis.
        """
        base_strategy = self.strategy_builder({})
        base_metrics = self._run_simple_backtest(base_strategy)

        parameter_results = []

        param_values_map = {}
        for param_name, param_range in config.parameters.items():
            param_values_map[param_name] = param_range.generate_values()

        for param_name, values in param_values_map.items():
            for value in values:
                test_params = {param_name: value}
                try:
                    strategy_fn = self.strategy_builder(test_params)
                    metrics = self._run_simple_backtest(strategy_fn)

                    parameter_results.append({
                        "parameter": param_name,
                        "value": value,
                        "metrics": metrics,
                    })
                except Exception:
                    pass

        sensitivity_scores = {}
        for param_name in config.parameters.keys():
            param_results = [r for r in parameter_results if r["parameter"] == param_name]
            if len(param_results) > 1:
                metric_values = [r["metrics"].get(metric, 0) for r in param_results]
                variance = np.var(metric_values) if metric_values else 0.0
                sensitivity_scores[param_name] = variance

        most_sensitive = sorted(sensitivity_scores.keys(), key=lambda x: sensitivity_scores[x], reverse=True)

        return SensitivityResult(
            strategy_name="strategy",
            metric_name=metric,
            base_metrics=base_metrics,
            parameter_results=parameter_results,
            most_sensitive=most_sensitive,
        )

    def save_result(self, result: SensitivityResult, output_path: str) -> Path:
        """Save sensitivity result to JSON."""
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with output_file.open("w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2, sort_keys=False)

        return output_file

    def print_tornado(self, result: SensitivityResult) -> None:
        """Print tornado chart (text table) to stdout."""
        print("\n" + "=" * 70)
        print(f"Sensitivity Analysis: {result.strategy_name}")
        print(f"Metric: {result.metric_name}")
        print("=" * 70)

        print("\n[Most Sensitive Parameters (sorted by variance)]")
        print(f"{'Rank':<6} {'Parameter':<20} {'Variance':<15}")
        print("-" * 41)

        sensitivity_scores = {}
        for param_result in result.parameter_results:
            param_name = param_result["parameter"]
            if param_name not in sensitivity_scores:
                sensitivity_scores[param_name] = []
            sensitivity_scores[param_name].append(param_result["metrics"].get(result.metric_name, 0))

        for param_name, values in sensitivity_scores.items():
            variance = np.var(values) if len(values) > 1 else 0.0
            print(f"{len([p for p in result.most_sensitive if sensitivity_scores[p][0] > variance]) + 1:<6} {param_name:<20} {variance:.6f}")

        print("\n[Tornado Table: Parameter Impact on Metric]")
        print(f"{'Parameter':<20} {'Min Value':<12} {'Max Value':<12} {'Range':<12}")
        print("-" * 56)

        for param_name in result.most_sensitive:
            param_results = [r for r in result.parameter_results if r["parameter"] == param_name]
            metric_values = [r["metrics"].get(result.metric_name, 0) for r in param_results]

            min_val = min(metric_values) if metric_values else 0
            max_val = max(metric_values) if metric_values else 0

            print(f"{param_name:<20} {min_val:<12.4f} {max_val:<12.4f} {max_val - min_val:<12.4f}")

        print("=" * 70)


def load_sensitivity_config(path: str) -> SensitivityConfig:
    """Load sensitivity configuration from JSON file."""
    with Path(path).open() as f:
        data = json.load(f)
    return SensitivityConfig.from_dict(data)