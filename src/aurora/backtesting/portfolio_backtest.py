"""Portfolio-level backtesting for multi-asset strategies.

This module provides research-only portfolio backtesting. No live trading, no broker calls.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd


@dataclass
class PortfolioBacktestResult:
    """Result from a portfolio backtest."""

    universe_name: str
    total_trades: int
    metrics: dict[str, float] = field(default_factory=dict)
    per_symbol_metrics: dict[str, dict[str, float]] = field(default_factory=dict)
    correlation_matrix: dict[str, dict[str, float]] = field(default_factory=dict)
    trades: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "universe_name": self.universe_name,
            "total_trades": self.total_trades,
            "metrics": self.metrics,
            "per_symbol_metrics": self.per_symbol_metrics,
            "correlation_matrix": self.correlation_matrix,
            "trades": self.trades,
        }


def run_portfolio_backtest(
    strategy_fn: Callable[[pd.DataFrame], pd.DataFrame],
    universe,
    start_date: str,
    end_date: str,
    initial_capital: float = 100000.0,
    weights: dict[str, float] | None = None,
    data_fetcher: Any = None,
) -> PortfolioBacktestResult:
    """Run portfolio backtest on a universe of symbols.

    Args:
        strategy_fn: Function that takes a DataFrame and returns DataFrame with signals.
        universe: Universe instance with symbols.
        start_date: Start date (YYYY-MM-DD).
        end_date: End date (YYYY-MM-DD).
        initial_capital: Initial capital for the portfolio.
        weights: Optional dict mapping symbol to weight. If None, equal weight.
        data_fetcher: Optional data fetcher. If None, uses YFinanceDataSource.

    Returns:
        PortfolioBacktestResult with portfolio metrics, per-symbol metrics, and correlation.
    """
    from aurora.data.universe import UniverseProvider

    if weights is None:
        weights = {symbol: 1.0 / len(universe.symbols) for symbol in universe.symbols}

    if data_fetcher is None:
        data_fetcher = UniverseProvider.fetch_data

    symbol_data = data_fetcher(universe, start_date, end_date)

    if not symbol_data:
        raise ValueError("No data fetched for any symbol in the universe")

    all_trades = []
    per_symbol_metrics = {}
    daily_returns = {}

    for symbol in universe.symbols:
        if symbol not in symbol_data:
            continue

        data = symbol_data[symbol].copy()

        try:
            result_df = strategy_fn(data)

            if "signal" not in result_df.columns:
                per_symbol_metrics[symbol] = {
                    "total_return": 0.0,
                    "sharpe_ratio": 0.0,
                    "max_drawdown": 0.0,
                    "win_rate": 0.0,
                    "trade_count": 0,
                }
                continue

            signals = result_df["signal"]
            close_prices = result_df["close"] if "close" in result_df.columns else result_df.get("adjusted_close", pd.Series(0, index=result_df.index))

            if close_prices.empty:
                close_prices = pd.Series(0, index=result_df.index)

            symbol_capital = initial_capital * weights.get(symbol, 0)
            position = 0
            entry_price = 0.0

            for i, (date, row) in enumerate(result_df.iterrows()):
                current_signal = signals.iloc[i] if i < len(signals) else 0

                if position == 0 and current_signal == 1:
                    position = 1
                    entry_price = close_prices.iloc[i] if i < len(close_prices) else 0

                elif position == 1 and current_signal == 0:
                    exit_price = close_prices.iloc[i] if i < len(close_prices) else 0
                    pnl = (exit_price - entry_price) / entry_price * symbol_capital if entry_price > 0 else 0

                    all_trades.append({
                        "symbol": symbol,
                        "entry_date": str(result_df.index[i - 1]) if i > 0 else str(date),
                        "exit_date": str(date),
                        "entry_price": float(entry_price),
                        "exit_price": float(exit_price),
                        "pnl": float(pnl),
                        "return_pct": float(pnl / symbol_capital) if symbol_capital > 0 else 0,
                    })

                    position = 0
                    entry_price = 0.0

            if position == 1:
                exit_price = close_prices.iloc[-1] if len(close_prices) > 0 else 0
                pnl = (exit_price - entry_price) / entry_price * symbol_capital if entry_price > 0 else 0

                all_trades.append({
                    "symbol": symbol,
                    "entry_date": str(result_df.index[-2]) if len(result_df) > 1 else str(result_df.index[0]),
                    "exit_date": str(result_df.index[-1]),
                    "entry_price": float(entry_price),
                    "exit_price": float(exit_price),
                    "pnl": float(pnl),
                    "return_pct": float(pnl / symbol_capital) if symbol_capital > 0 else 0,
                })

            if not all_trades:
                per_symbol_metrics[symbol] = {
                    "total_return": 0.0,
                    "sharpe_ratio": 0.0,
                    "max_drawdown": 0.0,
                    "win_rate": 0.0,
                    "trade_count": 0,
                }
                continue

            symbol_trades = [t["pnl"] for t in all_trades if t["symbol"] == symbol]
            total_return = sum(symbol_trades)
            wins = sum(1 for t in symbol_trades if t > 0)
            win_rate = wins / len(symbol_trades) if symbol_trades else 0.0

            equity = [0]
            for pnl in symbol_trades:
                equity.append(equity[-1] + pnl)

            peak = equity[0]
            max_dd = 0.0
            for eq in equity:
                if eq > peak:
                    peak = eq
                dd = (peak - eq) / max(peak, 1) if peak > 0 else 0
                if dd > max_dd:
                    max_dd = dd

            if "close" in result_df.columns:
                daily_rets = result_df["close"].pct_change().fillna(0)
            else:
                daily_rets = pd.Series(0, index=result_df.index)

            daily_returns[symbol] = daily_rets

            mean_ret = np.mean(daily_rets)
            std_ret = np.std(daily_rets, ddof=1) if len(daily_rets) > 1 else 0.0
            sharpe = (mean_ret / std_ret * np.sqrt(252)) if std_ret > 0 else 0.0

            per_symbol_metrics[symbol] = {
                "total_return": float(total_return),
                "sharpe_ratio": float(sharpe),
                "max_drawdown": float(max_dd),
                "win_rate": float(win_rate),
                "trade_count": len(symbol_trades),
            }

        except Exception as e:
            per_symbol_metrics[symbol] = {
                "total_return": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown": 0.0,
                "win_rate": 0.0,
                "trade_count": 0,
                "error": str(e),
            }

    if not daily_returns:
        correlation_matrix = {}
    else:
        returns_df = pd.DataFrame(daily_returns)
        corr = returns_df.corr()
        correlation_matrix = corr.to_dict()

    total_pnl = sum(t["pnl"] for t in all_trades)
    total_return = total_pnl / initial_capital

    wins = sum(1 for t in all_trades if t["pnl"] > 0)
    win_rate = wins / len(all_trades) if all_trades else 0.0

    equity = [0]
    for t in all_trades:
        equity.append(equity[-1] + t["pnl"])

    peak = equity[0]
    max_dd = 0.0
    for eq in equity:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / max(peak, 1) if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd

    portfolio_sharpe = 0.0
    if all_trades:
        trade_returns = [t["return_pct"] for t in all_trades]
        mean_ret = np.mean(trade_returns) if trade_returns else 0.0
        std_ret = np.std(trade_returns, ddof=1) if len(trade_returns) > 1 else 0.0
        portfolio_sharpe = (mean_ret / std_ret * np.sqrt(252)) if std_ret > 0 else 0.0

    metrics = {
        "total_return": float(total_return),
        "sharpe_ratio": float(portfolio_sharpe),
        "max_drawdown": float(max_dd),
        "win_rate": float(win_rate),
        "total_trades": len(all_trades),
    }

    return PortfolioBacktestResult(
        universe_name=universe.name,
        total_trades=len(all_trades),
        metrics=metrics,
        per_symbol_metrics=per_symbol_metrics,
        correlation_matrix=correlation_matrix,
        trades=all_trades,
    )


def save_portfolio_result(
    result: PortfolioBacktestResult,
    output_path: str,
    artifact_differ: Any = None,
) -> Path:
    """Save portfolio backtest result to JSON.

    Args:
        result: Portfolio backtest result.
        output_path: Path to save the JSON file.
        artifact_differ: Optional ArtifactDiffer for archiving previous version.

    Returns:
        Path to the saved file.
    """
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    artifact_name = output_file.stem

    if artifact_differ is not None and artifact_differ.is_enabled:
        artifact_differ.save_run_artifact(artifact_name, result.to_dict())

    with output_file.open("w", encoding="utf-8") as f:
        json.dump(result.to_dict(), f, indent=2, sort_keys=False)

    return output_file