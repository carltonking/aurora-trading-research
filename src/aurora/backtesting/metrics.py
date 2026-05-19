"""Backtest metric calculations."""

from dataclasses import asdict, dataclass

import pandas as pd


@dataclass(frozen=True)
class BacktestMetrics:
    """Summary metrics for a research backtest."""

    total_return: float
    annualized_return: float | None
    sharpe_ratio: float | None
    max_drawdown: float
    win_rate: float | None
    profit_factor: float | None
    average_win: float | None
    average_loss: float | None
    trade_count: int
    exposure_pct: float
    final_equity: float
    starting_equity: float


def calculate_equity_curve_metrics(
    equity_curve: pd.DataFrame,
    trades: pd.DataFrame,
    starting_cash: float,
    periods_per_year: int = 252,
) -> BacktestMetrics:
    """Calculate headline backtest metrics from equity and trades."""
    if equity_curve.empty:
        final_equity = float(starting_cash)
        equity = pd.Series([starting_cash], dtype=float)
        exposure = pd.Series([0.0], dtype=float)
    else:
        equity = pd.to_numeric(equity_curve["equity"], errors="coerce")
        exposure = pd.to_numeric(equity_curve["exposure"], errors="coerce").fillna(0.0)
        final_equity = float(equity.iloc[-1])

    total_return = final_equity / starting_cash - 1
    periods = len(equity)
    annualized_return = _annualized_return(total_return, periods, periods_per_year)
    sharpe_ratio = _sharpe_ratio(equity, periods_per_year)
    max_drawdown = _max_drawdown(equity)
    trade_metrics = _trade_metrics(trades)

    return BacktestMetrics(
        total_return=float(total_return),
        annualized_return=annualized_return,
        sharpe_ratio=sharpe_ratio,
        max_drawdown=max_drawdown,
        win_rate=trade_metrics["win_rate"],
        profit_factor=trade_metrics["profit_factor"],
        average_win=trade_metrics["average_win"],
        average_loss=trade_metrics["average_loss"],
        trade_count=int(trade_metrics["trade_count"]),
        exposure_pct=float((exposure > 0).mean()) if len(exposure) else 0.0,
        final_equity=final_equity,
        starting_equity=float(starting_cash),
    )


def metrics_to_dict(metrics: BacktestMetrics) -> dict:
    """Convert BacktestMetrics to a dictionary."""
    return asdict(metrics)


def _annualized_return(
    total_return: float,
    periods: int,
    periods_per_year: int,
) -> float | None:
    if periods <= 1:
        return None
    return float((1 + total_return) ** (periods_per_year / (periods - 1)) - 1)


def _sharpe_ratio(equity: pd.Series, periods_per_year: int) -> float | None:
    returns = equity.pct_change().dropna()
    if returns.empty or returns.std() == 0:
        return None
    return float((returns.mean() / returns.std()) * (periods_per_year**0.5))


def _max_drawdown(equity: pd.Series) -> float:
    running_max = equity.cummax()
    drawdown = equity / running_max - 1
    return float(drawdown.min()) if not drawdown.empty else 0.0


def _trade_metrics(trades: pd.DataFrame) -> dict:
    if trades.empty or "net_pnl" not in trades.columns:
        return {
            "win_rate": None,
            "profit_factor": None,
            "average_win": None,
            "average_loss": None,
            "trade_count": 0,
        }

    closed = trades.dropna(subset=["net_pnl"]).copy()
    if closed.empty:
        return {
            "win_rate": None,
            "profit_factor": None,
            "average_win": None,
            "average_loss": None,
            "trade_count": 0,
        }

    pnl = pd.to_numeric(closed["net_pnl"], errors="coerce").dropna()
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    gross_wins = float(wins.sum())
    gross_losses = float(losses.sum())

    return {
        "win_rate": float((pnl > 0).mean()),
        "profit_factor": (gross_wins / abs(gross_losses)) if gross_losses < 0 else None,
        "average_win": float(wins.mean()) if not wins.empty else None,
        "average_loss": float(losses.mean()) if not losses.empty else None,
        "trade_count": int(len(pnl)),
    }
