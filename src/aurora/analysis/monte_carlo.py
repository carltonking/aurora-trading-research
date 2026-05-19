"""Monte Carlo simulation for backtest results.

This module provides research-only Monte Carlo simulation to generate
distributions of possible strategy outcomes. No live trading, no broker calls.
"""

import json
import random
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class MonteCarloConfig:
    """Configuration for Monte Carlo simulation."""

    num_simulations: int = 1000
    method: str = "trade_reshuffle"
    random_seed: int | None = None

    def __post_init__(self) -> None:
        if self.method not in ("trade_reshuffle", "price_path"):
            raise ValueError(f"Invalid method: {self.method}. Must be 'trade_reshuffle' or 'price_path'.")
        if self.num_simulations < 1:
            raise ValueError("num_simulations must be >= 1")


@dataclass
class MonteCarloResult:
    """Result of Monte Carlo simulation."""

    strategy_name: str
    config_used: dict[str, Any]
    metrics_distribution: dict[str, list[float]] = field(default_factory=dict)
    summary_stats: dict[str, dict[str, float]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_name": self.strategy_name,
            "config_used": self.config_used,
            "metrics_distribution": self.metrics_distribution,
            "summary_stats": self.summary_stats,
        }


class MonteCarloSimulator:
    """Monte Carlo simulator for backtest results.

    This is a research-only simulator. It generates distributions of possible
    strategy outcomes by resampling trade sequences. No live trading, no broker calls.
    """

    def __init__(self, config: MonteCarloConfig) -> None:
        """Initialize Monte Carlo simulator.

        Args:
            config: Monte Carlo configuration.
        """
        self.config = config
        if config.random_seed is not None:
            random.seed(config.random_seed)
            np.random.seed(config.random_seed)

    def run(self, backtest_trades: list[dict], strategy_name: str = "unknown") -> MonteCarloResult:
        """Run Monte Carlo simulation on backtest trades.

        Args:
            backtest_trades: List of trade dictionaries with 'pnl' key.
            strategy_name: Name of the strategy being simulated.

        Returns:
            MonteCarloResult with metrics distribution and summary statistics.

        Raises:
            ValueError: If no trades provided or invalid config.
            NotImplementedError: If method is 'price_path'.
        """
        if not backtest_trades:
            raise ValueError("No trades provided for simulation")

        if self.config.method == "trade_reshuffle":
            return self._run_trade_reshuffle(backtest_trades, strategy_name)
        elif self.config.method == "price_path":
            raise NotImplementedError("Price path simulation not yet implemented.")

    def _run_trade_reshuffle(self, trades: list[dict], strategy_name: str) -> MonteCarloResult:
        """Run trade reshuffle Monte Carlo simulation."""
        pnls = [t["pnl"] for t in trades if "pnl" in t]
        if not pnls:
            raise ValueError("No P&L values found in trades")

        num_trades = len(pnls)

        total_returns = []
        sharpe_ratios = []
        max_drawdowns = []
        win_rates = []

        starting_equity = 100000.0

        for _ in range(self.config.num_simulations):
            sampled_pnls = random.choices(pnls, k=num_trades)

            equity_curve = [starting_equity]
            for pnl in sampled_pnls:
                equity_curve.append(equity_curve[-1] + pnl)

            total_return = (equity_curve[-1] - starting_equity) / starting_equity
            total_returns.append(total_return)

            daily_returns = []
            for i in range(1, len(equity_curve)):
                daily_returns.append((equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1])

            if daily_returns:
                mean_return = np.mean(daily_returns)
                std_return = np.std(daily_returns, ddof=1) if len(daily_returns) > 1 else 0.0
                if std_return > 0:
                    sharpe = (mean_return / std_return) * np.sqrt(252)
                else:
                    sharpe = 0.0
            else:
                sharpe = 0.0
            sharpe_ratios.append(sharpe)

            peak = equity_curve[0]
            max_dd = 0.0
            for eq in equity_curve:
                if eq > peak:
                    peak = eq
                dd = (peak - eq) / peak
                if dd > max_dd:
                    max_dd = dd
            max_drawdowns.append(max_dd)

            wins = sum(1 for p in sampled_pnls if p > 0)
            win_rate = wins / len(sampled_pnls) if sampled_pnls else 0.0
            win_rates.append(win_rate)

        metrics_distribution = {
            "total_return": total_returns,
            "sharpe_ratio": sharpe_ratios,
            "max_drawdown": max_drawdowns,
            "win_rate": win_rates,
        }

        summary_stats = {}
        for metric_name, values in metrics_distribution.items():
            summary_stats[metric_name] = {
                "mean": float(np.mean(values)),
                "median": float(np.median(values)),
                "std": float(np.std(values, ddof=1)) if len(values) > 1 else 0.0,
                "p5": float(np.percentile(values, 5)),
                "p95": float(np.percentile(values, 95)),
            }

        config_dict = {
            "num_simulations": self.config.num_simulations,
            "method": self.config.method,
            "random_seed": self.config.random_seed,
        }

        return MonteCarloResult(
            strategy_name=strategy_name,
            config_used=config_dict,
            metrics_distribution=metrics_distribution,
            summary_stats=summary_stats,
        )

    def save_result(self, result: MonteCarloResult, output_path: str) -> Path:
        """Save Monte Carlo result to JSON file.

        Args:
            result: Monte Carlo result to save.
            output_path: Path to save the JSON file.

        Returns:
            Path to the saved file.
        """
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with output_file.open("w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2, sort_keys=False)

        return output_file


def load_trades_from_backtest(backtest_json_path: str) -> list[dict]:
    """Load trades from backtest JSON and associated trades CSV.

    Args:
        backtest_json_path: Path to backtest.json file.

    Returns:
        List of trade dictionaries with 'pnl' key.
    """
    backtest_path = Path(backtest_json_path)
    if not backtest_path.exists():
        raise FileNotFoundError(f"Backtest file not found: {backtest_json_path}")

    with backtest_path.open() as f:
        backtest_data = json.load(f)

    trades_path = backtest_data.get("trades_path")
    if not trades_path:
        return []

    trades_file = backtest_path.parent / Path(trades_path).name
    if not trades_file.exists():
        return []

    import pandas as pd
    df = pd.read_csv(trades_file)

    trades = []
    for _, row in df.iterrows():
        trades.append({
            "trade_id": row.get("trade_id"),
            "symbol": row.get("symbol"),
            "entry_timestamp": str(row.get("entry_timestamp")),
            "exit_timestamp": str(row.get("exit_timestamp")),
            "pnl": float(row.get("net_pnl", 0)),
            "return_pct": float(row.get("return_pct", 0)),
        })

    return trades