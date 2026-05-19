"""Paper performance metrics collection and analysis.

This module provides research-only performance metrics from the paper execution ledger.
No live trading, no broker calls, no profitability claims.
"""

import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass
class PaperMetrics:
    """Paper trading performance metrics."""

    strategy_name: str
    start_date: str | None = None
    end_date: str | None = None
    total_trades: int = 0
    win_count: int = 0
    loss_count: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    avg_pnl_per_trade: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    profit_factor: float = 0.0
    avg_slippage: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_name": self.strategy_name,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "total_trades": self.total_trades,
            "win_count": self.win_count,
            "loss_count": self.loss_count,
            "win_rate": self.win_rate,
            "total_pnl": self.total_pnl,
            "avg_pnl_per_trade": self.avg_pnl_per_trade,
            "max_drawdown": self.max_drawdown,
            "sharpe_ratio": self.sharpe_ratio,
            "profit_factor": self.profit_factor,
            "avg_slippage": self.avg_slippage,
            "timestamp": self.timestamp,
        }


class PaperPerformanceAnalyzer:
    """Research-only paper performance analyzer.

    Analyzes paper execution ledger to compute performance metrics.
    P&L estimation uses placeholder price movement; real fill data to be integrated later.
    """

    PLACEHOLDER_PNL_NOTE = "P&L estimation uses placeholder price movement; real fill data to be integrated later."

    def __init__(self, ledger_path: str | None = None) -> None:
        self.ledger_path = ledger_path or os.getenv(
            "AURORA_PAPER_LEDGER_PATH",
            "data/paper_ledger/execution_log.jsonl",
        )

    def load_trades(self, strategy_name: str | None = None) -> list[dict[str, Any]]:
        """Load trades from ledger, filtering for APPROVED orders only.

        Args:
            strategy_name: Optional filter for strategy name.

        Returns:
            List of trade dictionaries from the ledger.
        """
        path = Path(self.ledger_path)
        if not path.exists():
            return []

        trades = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                risk_decision = entry.get("risk_decision", {})
                if not risk_decision:
                    continue

                status = risk_decision.get("status")
                if status != "APPROVED":
                    continue

                if strategy_name:
                    request = entry.get("request", {})
                    if request.get("strategy_name") != strategy_name:
                        continue

                trades.append(entry)

        return trades

    def compute_metrics(self, strategy_name: str | None = None) -> PaperMetrics:
        """Compute performance metrics from loaded trades.

        Args:
            strategy_name: Optional filter for strategy name.

        Returns:
            PaperMetrics with computed performance data.
        """
        trades = self.load_trades(strategy_name)

        if not trades:
            return PaperMetrics(
                strategy_name=strategy_name or "unknown",
                start_date=None,
                end_date=None,
            )

        strategy = strategy_name or trades[0].get("request", {}).get("strategy_name", "unknown")

        timestamps = []
        pnls = []
        wins = 0
        losses = 0

        for trade in trades:
            request = trade.get("request", {})
            timestamp = request.get("timestamp")
            if timestamp:
                timestamps.append(timestamp)

            pnl = self._estimate_pnl(trade)
            pnls.append(pnl)

            if pnl > 0:
                wins += 1
            elif pnl < 0:
                losses += 1

        if not pnls:
            return PaperMetrics(strategy_name=strategy)

        timestamps.sort()
        start_date = timestamps[0] if timestamps else None
        end_date = timestamps[-1] if timestamps else None

        total_trades = len(pnls)
        total_pnl = sum(pnls)
        avg_pnl = total_pnl / total_trades if total_trades > 0 else 0.0

        win_rate = wins / total_trades if total_trades > 0 else 0.0
        win_count = wins
        loss_count = losses

        cumulative = []
        running = 0.0
        peak = 0.0
        max_dd = 0.0
        for p in pnls:
            running += p
            if running > peak:
                peak = running
            dd = peak - running
            if dd > max_dd:
                max_dd = dd
            cumulative.append(running)

        gross_wins = sum(p for p in pnls if p > 0)
        gross_losses = abs(sum(p for p in pnls if p < 0))
        profit_factor = gross_wins / gross_losses if gross_losses > 0 else 0.0

        if len(pnls) > 1:
            returns = pd.Series(pnls)
            std = returns.std()
            if std > 0:
                sharpe = (returns.mean() / std) * (252 ** 0.5)
            else:
                sharpe = 0.0
        else:
            sharpe = 0.0

        return PaperMetrics(
            strategy_name=strategy,
            start_date=start_date,
            end_date=end_date,
            total_trades=total_trades,
            win_count=win_count,
            loss_count=loss_count,
            win_rate=win_rate,
            total_pnl=total_pnl,
            avg_pnl_per_trade=avg_pnl,
            max_drawdown=max_dd,
            sharpe_ratio=sharpe,
            profit_factor=profit_factor,
            avg_slippage=0.0,
        )

    def _estimate_pnl(self, trade: dict[str, Any]) -> float:
        """Estimate P&L using placeholder price movement.

        Note: This is placeholder logic. Real fill data to be integrated later.
        """
        request = trade.get("request", {})
        side = request.get("side", "")
        quantity = request.get("quantity", 0)
        price = request.get("price", 0.0)

        if quantity <= 0 or price <= 0:
            return 0.0

        if side == "buy":
            placeholder_return = 0.005
        else:
            placeholder_return = -0.003

        pnl = quantity * price * placeholder_return
        return pnl


def save_metrics(metrics: PaperMetrics, output_dir: str) -> Path:
    """Save paper performance metrics to JSON file.

    Args:
        metrics: PaperMetrics to save.
        output_dir: Directory to write the metrics file.

    Returns:
        Path to the written file.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    file_path = output_path / "paper_performance.json"
    with file_path.open("w", encoding="utf-8") as f:
        json.dump(metrics.to_dict(), f, indent=2, sort_keys=True)

    return file_path