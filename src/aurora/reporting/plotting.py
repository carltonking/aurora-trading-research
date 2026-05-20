"""Equity curve plotting for backtest/paper trading results.

This module provides matplotlib-based charting for research results.
Matplotlib is optional - if not available, functions return early with a warning.
Charts are research-only, no profitability claims.
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    logger.warning("matplotlib not available. Plotting functions will be no-ops.")


def plot_equity_curve(
    equity_series: "pd.Series",
    trades: Optional[list[dict]] = None,
    output_path: Optional[str] = None,
    title: str = "Equity Curve",
    show: bool = False,
) -> None:
    """Plot equity curve with optional trade markers.

    Args:
        equity_series: Series of equity values over time.
        trades: Optional list of trade dicts with 'pnl' and 'exit_time' keys.
        output_path: Optional path to save PNG.
        title: Chart title.
        show: If True, call plt.show() (blocks).
    """
    if not MATPLOTLIB_AVAILABLE:
        logger.warning("matplotlib not available, skipping equity curve plot.")
        return

    fig, ax = plt.subplots(figsize=(12, 6))

    ax.plot(equity_series.index, equity_series.values, color="#2E86AB", linewidth=1.5, label="Portfolio Value")

    if trades:
        winning_trades = [t for t in trades if t.get("pnl", 0) > 0]
        losing_trades = [t for t in trades if t.get("pnl", 0) <= 0]

        if winning_trades:
            exit_times = [t["exit_time"] for t in winning_trades if "exit_time" in t]
            exit_values = []
            for t in winning_trades:
                if "exit_time" in t:
                    idx = equity_series.index.get_indexer([t["exit_time"]], method="nearest")[0]
                    if 0 <= idx < len(equity_series):
                        exit_values.append(equity_series.iloc[idx])

            if exit_times and exit_values:
                ax.scatter(exit_times[:len(exit_values)], exit_values, marker="^", color="#2ECC71", s=50, label="Win", zorder=5)

        if losing_trades:
            exit_times = [t["exit_time"] for t in losing_trades if "exit_time" in t]
            exit_values = []
            for t in losing_trades:
                if "exit_time" in t:
                    idx = equity_series.index.get_indexer([t["exit_time"]], method="nearest")[0]
                    if 0 <= idx < len(equity_series):
                        exit_values.append(equity_series.iloc[idx])

            if exit_times and exit_values:
                ax.scatter(exit_times[:len(exit_values)], exit_values, marker="v", color="#E74C3C", s=50, label="Loss", zorder=5)

    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.set_xlabel("Date", fontsize=11)
    ax.set_ylabel("Portfolio Value", fontsize=11)
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)

    plt.tight_layout()

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        logger.info(f"Equity curve saved to {output_path}")

    if show:
        plt.show()

    plt.close(fig)


def plot_drawdown(
    equity_series: "pd.Series",
    output_path: Optional[str] = None,
    title: str = "Drawdown",
    show: bool = False,
) -> None:
    """Plot drawdown as negative area from peak.

    Args:
        equity_series: Series of equity values over time.
        output_path: Optional path to save PNG.
        title: Chart title.
        show: If True, call plt.show() (blocks).
    """
    if not MATPLOTLIB_AVAILABLE:
        logger.warning("matplotlib not available, skipping drawdown plot.")
        return

    running_max = equity_series.expanding().max()
    drawdown = (equity_series - running_max) / running_max

    fig, ax = plt.subplots(figsize=(12, 4))

    ax.fill_between(drawdown.index, drawdown.values, 0, color="#E74C3C", alpha=0.4, label="Drawdown")
    ax.plot(drawdown.index, drawdown.values, color="#E74C3C", linewidth=0.8)

    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.set_xlabel("Date", fontsize=11)
    ax.set_ylabel("Drawdown %", fontsize=11)
    ax.legend(loc="lower left")
    ax.grid(True, alpha=0.3)

    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:.0%}"))

    plt.tight_layout()

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        logger.info(f"Drawdown plot saved to {output_path}")

    if show:
        plt.show()

    plt.close(fig)


def plot_rolling_sharpe(
    returns_series: "pd.Series",
    window: int = 60,
    output_path: Optional[str] = None,
    title: str = "Rolling Sharpe Ratio",
    show: bool = False,
) -> None:
    """Plot rolling Sharpe ratio (annualized).

    Args:
        returns_series: Series of periodic returns.
        window: Rolling window size (default 60 for daily).
        output_path: Optional path to save PNG.
        title: Chart title.
        show: If True, call plt.show() (blocks).
    """
    if not MATPLOTLIB_AVAILABLE:
        logger.warning("matplotlib not available, skipping rolling Sharpe plot.")
        return

    rolling_mean = returns_series.rolling(window).mean()
    rolling_std = returns_series.rolling(window).std()

    with_warning = rolling_std.replace(0, float("nan"))
    rolling_sharpe = (rolling_mean / with_warning) * (252 ** 0.5)

    fig, ax = plt.subplots(figsize=(12, 4))

    ax.plot(rolling_sharpe.index, rolling_sharpe.values, color="#9B59B6", linewidth=1.2, label=f"{window}-period Sharpe")
    ax.axhline(y=0, color="#7F8C8D", linestyle="--", linewidth=1)
    ax.axhline(y=1, color="#27AE60", linestyle="--", linewidth=0.8, alpha=0.7)
    ax.axhline(y=-1, color="#E74C3C", linestyle="--", linewidth=0.8, alpha=0.7)

    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.set_xlabel("Date", fontsize=11)
    ax.set_ylabel("Sharpe Ratio", fontsize=11)
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)

    plt.tight_layout()

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        logger.info(f"Rolling Sharpe plot saved to {output_path}")

    if show:
        plt.show()

    plt.close(fig)


def plot_combined_report(
    equity_series: "pd.Series",
    trades: Optional[list[dict]] = None,
    rolling_sharpe_window: int = 60,
    output_dir: str = "data/reports",
) -> str | None:
    """Generate combined multi-panel performance chart.

    Args:
        equity_series: Series of equity values over time.
        trades: Optional list of trade dicts.
        rolling_sharpe_window: Window for rolling Sharpe.
        output_dir: Directory to save the chart.

    Returns:
        Path to saved chart, or None if matplotlib unavailable.
    """
    if not MATPLOTLIB_AVAILABLE:
        logger.warning("matplotlib not available, skipping combined report.")
        return None

    running_max = equity_series.expanding().max()
    drawdown = (equity_series - running_max) / running_max

    returns = equity_series.pct_change().dropna()
    rolling_mean = returns.rolling(rolling_sharpe_window).mean()
    rolling_std = returns.rolling(rolling_sharpe_window).std()

    with_warning = rolling_std.replace(0, float("nan"))
    rolling_sharpe = (rolling_mean / with_warning) * (252 ** 0.5)

    fig, axes = plt.subplots(3, 1, figsize=(12, 12), sharex=True)

    axes[0].plot(equity_series.index, equity_series.values, color="#2E86AB", linewidth=1.5)
    axes[0].set_title("Portfolio Value", fontsize=12, fontweight="bold")
    axes[0].set_ylabel("Value", fontsize=10)
    axes[0].grid(True, alpha=0.3)

    axes[1].fill_between(drawdown.index, drawdown.values, 0, color="#E74C3C", alpha=0.4)
    axes[1].plot(drawdown.index, drawdown.values, color="#E74C3C", linewidth=0.8)
    axes[1].set_title("Drawdown", fontsize=12, fontweight="bold")
    axes[1].set_ylabel("Drawdown %", fontsize=10)
    axes[1].yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:.0%}"))
    axes[1].grid(True, alpha=0.3)

    axes[2].plot(rolling_sharpe.index, rolling_sharpe.values, color="#9B59B6", linewidth=1.2)
    axes[2].axhline(y=0, color="#7F8C8D", linestyle="--", linewidth=1)
    axes[2].set_title(f"Rolling Sharpe ({rolling_sharpe_window}-period)", fontsize=12, fontweight="bold")
    axes[2].set_xlabel("Date", fontsize=10)
    axes[2].set_ylabel("Sharpe", fontsize=10)
    axes[2].grid(True, alpha=0.3)

    plt.tight_layout()

    output_path = Path(output_dir) / "performance_chart.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    logger.info(f"Combined performance chart saved to {output_path}")

    plt.close(fig)

    return str(output_path)