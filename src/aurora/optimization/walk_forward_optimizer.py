"""Walk-forward optimizer for true out-of-sample testing."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

import pandas as pd


@dataclass
class WindowResult:
    """Result of a single walk-forward window."""

    train_start: str
    train_end: str
    test_start: str
    test_end: str
    best_params: dict[str, Any]
    train_metric: float
    oos_metric: float
    trades: int = 0
    oos_return: float = 0.0


@dataclass
class WalkForwardResult:
    """Complete result from walk-forward optimization."""

    windows: list[WindowResult] = field(default_factory=list)
    overall_oos_metrics: dict[str, float] = field(default_factory=dict)
    optimization_history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "windows": [
                {
                    "train_start": w.train_start,
                    "train_end": w.train_end,
                    "test_start": w.test_start,
                    "test_end": w.test_end,
                    "best_params": w.best_params,
                    "train_metric": w.train_metric,
                    "oos_metric": w.oos_metric,
                    "trades": w.trades,
                    "oos_return": w.oos_return,
                }
                for w in self.windows
            ],
            "overall_oos_metrics": self.overall_oos_metrics,
            "optimization_history": self.optimization_history,
        }


@dataclass
class WalkForwardOptimizerConfig:
    """Configuration for walk-forward optimizer."""

    strategy_archetype: str
    param_space: dict[str, dict[str, Any]]
    train_ratio: float = 0.6
    anchor: bool = True
    purge_days: int = 0
    embargo_days: int = 0
    reoptimize_freq: str = "monthly"
    metric: str = "sharpe_ratio"
    inner_optimizer: str = "genetic"
    inner_optimizer_kwargs: dict[str, Any] = field(default_factory=dict)


class WalkForwardOptimizer:
    """Walk-forward optimizer for out-of-sample testing.

    This optimizer is research-only and does not call any broker.
    """

    def __init__(
        self,
        config: WalkForwardOptimizerConfig,
        strategy_builder: Callable[[dict[str, Any]], Any],
        data_fetcher: Callable[[str, str, str], pd.DataFrame],
    ):
        """Initialize walk-forward optimizer.

        Args:
            config: Walk-forward configuration.
            strategy_builder: Function that takes params dict, returns strategy.
            data_fetcher: Function taking (symbol, start_date, end_date) returns DataFrame.
        """
        self.config = config
        self.strategy_builder = strategy_builder
        self.data_fetcher = data_fetcher

    def run(
        self,
        symbol: str,
        overall_start: str,
        overall_end: str,
    ) -> WalkForwardResult:
        """Run walk-forward optimization.

        Args:
            symbol: Stock symbol to optimize.
            overall_start: Start date for entire period.
            overall_end: End date for entire period.

        Returns:
            WalkForwardResult with all window results and overall metrics.
        """
        full_data = self.data_fetcher(symbol, overall_start, overall_end)

        if len(full_data) < 60:
            raise ValueError("Insufficient data for walk-forward optimization")

        windows = self._create_windows(full_data, overall_start, overall_end)

        results = []
        optimization_history = []

        for i, (train_start, train_end, test_start, test_end) in enumerate(windows):
            train_data = full_data[train_start:train_end]
            test_data = full_data[test_start:test_end]

            if len(train_data) < 30 or len(test_data) < 10:
                continue

            best_params, train_metric = self._optimize_window(train_data)

            oos_metrics = self._backtest_on_data(
                best_params,
                test_data,
            )

            window_result = WindowResult(
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
                best_params=best_params,
                train_metric=train_metric,
                oos_metric=oos_metrics.get(self.config.metric, 0.0),
                trades=oos_metrics.get("trades", 0),
                oos_return=oos_metrics.get("total_return", 0.0),
            )
            results.append(window_result)
            optimization_history.append(best_params)

        overall_oos = self._compute_overall_metrics(results)

        return WalkForwardResult(
            windows=results,
            overall_oos_metrics=overall_oos,
            optimization_history=optimization_history,
        )

    def _create_windows(
        self,
        data: pd.DataFrame,
        overall_start: str,
        overall_end: str,
    ) -> list[tuple[str, str, str, str]]:
        """Create train/test windows based on config."""
        dates = pd.date_range(start=overall_start, end=overall_end, freq="D")
        n_dates = len(dates)

        train_size = int(n_dates * self.config.train_ratio)

        if self.config.reoptimize_freq == "monthly":
            freq_days = 30
        elif self.config.reoptimize_freq == "quarterly":
            freq_days = 90
        else:
            freq_days = 60

        windows = []
        step = freq_days

        if self.config.anchor:
            for test_start_idx in range(train_size, n_dates - freq_days, step):
                test_end_idx = min(test_start_idx + freq_days, n_dates)

                train_end = dates[train_size - 1].strftime("%Y-%m-%d")
                test_start = dates[test_start_idx].strftime("%Y-%m-%d")
                test_end = dates[test_end_idx - 1].strftime("%Y-%m-%d")

                train_start = dates[0].strftime("%Y-%m-%d")

                if self.config.purge_days > 0:
                    purge_idx = test_start_idx - self.config.purge_days
                    if purge_idx > train_size:
                        train_end = dates[purge_idx - 1].strftime("%Y-%m-%d")

                if self.config.embargo_days > 0:
                    embargo_idx = train_size + self.config.embargo_days
                    if test_start_idx < embargo_idx:
                        test_start = dates[embargo_idx].strftime("%Y-%m-%d")

                windows.append((train_start, train_end, test_start, test_end))
        else:
            for test_start_idx in range(train_size, n_dates - freq_days, step):
                test_end_idx = min(test_start_idx + freq_days, n_dates)
                test_start_idx_adj = test_start_idx - self.config.purge_days if self.config.purge_days > 0 else test_start_idx
                train_start_idx = max(0, test_start_idx_adj - train_size)
                train_start = dates[train_start_idx].strftime("%Y-%m-%d")
                train_end = dates[test_start_idx - 1].strftime("%Y-%m-%d")
                test_start = dates[test_start_idx].strftime("%Y-%m-%d")
                test_end = dates[test_end_idx - 1].strftime("%Y-%m-%d")

                windows.append((train_start, train_end, test_start, test_end))

        return windows

    def _optimize_window(self, train_data: pd.DataFrame) -> tuple[dict[str, Any], float]:
        """Optimize parameters on training data."""
        from aurora.optimization.advanced.genetic import GeneticOptimizer

        def fitness_fn(params: dict) -> float:
            try:
                strategy = self.strategy_builder(params)
                signals = strategy.generate_signal(train_data)

                if self.config.metric == "sharpe_ratio":
                    returns = train_data["close"].pct_change()
                    if signals.iloc[-1] == 1:
                        returns = returns
                    else:
                        returns = returns * 0

                    if len(returns) < 5:
                        return 0.0

                    mean_ret = returns.mean()
                    std_ret = returns.std()
                    if std_ret > 0:
                        sharpe = mean_ret / std_ret * (252 ** 0.5)
                        return sharpe
                    return 0.0
                elif self.config.metric == "total_return":
                    if signals.iloc[-1] == 1:
                        return (train_data["close"].iloc[-1] / train_data["close"].iloc[0]) - 1
                    return 0.0
                return 0.0
            except Exception:
                return 0.0

        kwargs = self.config.inner_optimizer_kwargs.copy()
        kwargs["param_space"] = self.config.param_space
        kwargs["fitness_fn"] = fitness_fn

        if self.config.inner_optimizer == "genetic":
            optimizer = GeneticOptimizer(**kwargs)
        else:
            from aurora.optimization.advanced.bayesian import BayesianOptimizer
            optimizer = BayesianOptimizer(**kwargs)

        result = optimizer.optimize()
        return result.parameters, result.fitness

    def _backtest_on_data(
        self,
        params: dict[str, Any],
        test_data: pd.DataFrame,
    ) -> dict[str, float]:
        """Run backtest on test data and return metrics."""
        try:
            strategy = self.strategy_builder(params)
            signals = strategy.generate_signal(test_data)

            returns = test_data["close"].pct_change()
            if signals.sum() == 0:
                returns = returns * 0

            total_return = (1 + returns).prod() - 1

            if len(returns) > 0:
                mean_ret = returns.mean()
                std_ret = returns.std()
                if std_ret > 0:
                    sharpe = mean_ret / std_ret * (252 ** 0.5)
                else:
                    sharpe = 0.0
            else:
                sharpe = 0.0

            return {
                "total_return": total_return,
                "sharpe_ratio": sharpe,
                "trades": int(signals.abs().sum()),
            }
        except Exception:
            return {"total_return": 0.0, "sharpe_ratio": 0.0, "trades": 0}

    def _compute_overall_metrics(self, results: list[WindowResult]) -> dict[str, float]:
        """Compute overall out-of-sample metrics."""
        if not results:
            return {"sharpe_ratio": 0.0, "total_return": 0.0, "win_rate": 0.0}

        total_return = sum(w.oos_return for w in results)
        total_trades = sum(w.trades for w in results)

        sharpe_sum = sum(w.oos_metric for w in results)
        avg_sharpe = sharpe_sum / len(results) if results else 0.0

        return {
            "sharpe_ratio": avg_sharpe,
            "total_return": total_return,
            "total_trades": total_trades,
            "n_windows": len(results),
        }