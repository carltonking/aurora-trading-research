"""Combinatorial Purged Cross-Validation (CPCV) for financial time series.

Based on Marcos López de Prado, "Advances in Financial Machine Learning", Chapter 12.
CPCV generates multiple train/test paths through combinatorial selection of groups,
with purging and embargo to prevent information leakage. This produces a distribution
of performance metrics rather than a single point estimate, enabling detection of
backtest overfitting.

This module is research-only. No live trading, no broker calls.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from itertools import combinations
from typing import Any, Callable, Iterator

import numpy as np
import pandas as pd


MANDATORY_DISCLAIMER = (
    "Combinatorial Purged Cross-Validation is a research tool for estimating "
    "backtest overfitting risk. Results are not profitability guarantees. "
    "AURORA is research-only. Past performance does not guarantee future results."
)


@dataclass(frozen=True)
class CPCVConfig:
    """Configuration for CPCV validation."""

    n_splits: int = 6
    n_test_splits: int = 2
    purge_days: int = 21
    embargo_days: int = 5
    timestamp_col: str = "timestamp"
    signal_col: str = "signal"
    price_col: str = "close"
    starting_cash: float = 100000.0
    position_size_pct: float = 0.05
    commission_per_trade: float = 0.0
    slippage_bps: float = 5.0


@dataclass(frozen=True)
class CPCVSplit:
    """Single train/test split from CPCV."""

    path_id: int
    train_indices: np.ndarray
    test_indices: np.ndarray
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    train_start: pd.Timestamp | None
    train_end: pd.Timestamp | None


@dataclass
class BacktestPathResult:
    """Backtest result for a single CPCV path."""

    path_id: int
    train_start: str | None
    train_end: str | None
    test_start: str
    test_end: str
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    trade_count: int
    win_rate: float
    profit_factor: float
    equity_curve: list[float]
    passed: bool
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["equity_curve"] = self.equity_curve
        return result


@dataclass
class CPCVResult:
    """Full CPCV validation result."""

    config: CPCVConfig
    paths: list[BacktestPathResult]
    splits: list[CPCVSplit]
    created_at: str
    summary: dict[str, Any]
    disclaimer: str = MANDATORY_DISCLAIMER

    def to_dict(self) -> dict[str, Any]:
        return {
            "config": asdict(self.config),
            "paths": [p.to_dict() for p in self.paths],
            "splits": [
                {
                    "path_id": s.path_id,
                    "train_size": len(s.train_indices),
                    "test_size": len(s.test_indices),
                    "test_start": s.test_start.isoformat() if s.test_start else None,
                    "test_end": s.test_end.isoformat() if s.test_end else None,
                    "train_start": s.train_start.isoformat() if s.train_start else None,
                    "train_end": s.train_end.isoformat() if s.train_end else None,
                }
                for s in self.splits
            ],
            "created_at": self.created_at,
            "summary": self.summary,
            "disclaimer": self.disclaimer,
        }


def generate_cpcv_splits(
    df: pd.DataFrame,
    config: CPCVConfig,
) -> list[CPCVSplit]:
    """Generate all combinatorial train/test splits with purge and embargo.

    Args:
        df: DataFrame with timestamps and signals.
        config: CPCV configuration.

    Returns:
        List of CPCVSplit objects covering all valid combinatorial selections.

    Raises:
        ValueError: If parameters are invalid or insufficient data.
    """
    if config.n_test_splits > config.n_splits:
        raise ValueError("n_test_splits must be <= n_splits")
    if config.n_splits < 2:
        raise ValueError("n_splits must be >= 2")

    timestamps = pd.to_datetime(df[config.timestamp_col]).dropna().unique()
    timestamps = np.sort(timestamps)
    n_dates = len(timestamps)

    if n_dates < config.n_splits * 10:
        raise ValueError(
            f"Insufficient data: {n_dates} unique timestamps, "
            f"need at least {config.n_splits * 10}"
        )

    group_size = n_dates // config.n_splits
    if group_size < 1:
        raise ValueError(
            f"n_splits {config.n_splits} too large for {n_dates} dates"
        )

    groups = np.array_split(np.arange(n_dates), config.n_splits)
    group_boundaries = [
        (int(g[0]), int(g[-1])) for g in groups
    ]

    purge_buffer = config.purge_days
    embargo_buffer = config.embargo_days

    splits: list[CPCVSplit] = []
    path_id = 0

    for test_group_indices in combinations(range(config.n_splits), config.n_test_splits):
        test_indices_raw: set[int] = set()
        for gi in test_group_indices:
            test_indices_raw.update(groups[gi])

        test_indices_raw = set(test_indices_raw)
        train_indices_raw: set[int] = set()
        for gi in range(config.n_splits):
            if gi not in test_group_indices:
                train_indices_raw.update(groups[gi])

        test_sorted = sorted(test_indices_raw)
        test_dates = timestamps[test_sorted]
        test_start = pd.Timestamp(test_dates[0])
        test_end = pd.Timestamp(test_dates[-1])

        purge_start = test_start
        purge_end = test_start + pd.Timedelta(days=purge_buffer)

        embargo_start = test_end
        embargo_end = test_end + pd.Timedelta(days=embargo_buffer)

        train_indices: list[int] = []
        train_dates = timestamps[list(train_indices_raw)]
        train_start = pd.Timestamp(train_dates.min()) if len(train_dates) > 0 else None
        train_end = pd.Timestamp(train_dates.max()) if len(train_dates) > 0 else None

        for idx in sorted(train_indices_raw):
            ts = timestamps[idx]
            if ts < purge_start or (purge_start <= ts <= purge_end):
                continue
            if embargo_start <= ts <= embargo_end:
                continue
            train_indices.append(idx)

        test_indices_final = np.array(sorted(test_sorted), dtype=np.intp)

        if len(train_indices) < 10 or len(test_indices_final) < 3:
            continue

        splits.append(
            CPCVSplit(
                path_id=path_id,
                train_indices=np.array(train_indices, dtype=np.intp),
                test_indices=test_indices_final,
                test_start=test_start,
                test_end=test_end,
                train_start=train_start,
                train_end=train_end,
            )
        )
        path_id += 1

    return splits


def compute_cpcv_paths(
    df: pd.DataFrame,
    splits: list[CPCVSplit],
    config: CPCVConfig,
) -> list[BacktestPathResult]:
    """Run backtest on each CPCV path.

    Args:
        df: DataFrame with OHLCV data and signals.
        splits: List of CPCV splits from generate_cpcv_splits.
        config: CPCV configuration.

    Returns:
        List of BacktestPathResult objects, one per path.
    """
    timestamps = pd.to_datetime(df[config.timestamp_col]).dropna()
    timestamp_array = timestamps.values
    close_array = df[config.price_col].values

    results: list[BacktestPathResult] = []

    for split in splits:
        train_mask = np.zeros(len(df), dtype=bool)
        train_mask[split.train_indices] = True

        test_mask = np.zeros(len(df), dtype=bool)
        test_mask[split.test_indices] = True

        train_df = df[train_mask].copy()
        test_df = df[test_mask].copy()

        if len(test_df) < 3:
            results.append(
                BacktestPathResult(
                    path_id=split.path_id,
                    train_start=split.train_start.isoformat() if split.train_start else None,
                    train_end=split.train_end.isoformat() if split.train_end else None,
                    test_start=split.test_start.isoformat(),
                    test_end=split.test_end.isoformat(),
                    total_return=0.0,
                    sharpe_ratio=0.0,
                    max_drawdown=0.0,
                    trade_count=0,
                    win_rate=0.0,
                    profit_factor=0.0,
                    equity_curve=[config.starting_cash],
                    passed=False,
                    issues=["insufficient test data"],
                )
            )
            continue

        equity = [config.starting_cash]
        position = 0
        trades = 0
        wins = 0
        gross_profit = 0.0
        gross_loss = 0.0
        peak = config.starting_cash
        max_dd = 0.0

        signals = test_df[config.signal_col].values
        closes = test_df[config.price_col].values
        timestamps_test = test_df[config.timestamp_col].values

        entry_price = 0.0
        entry_side = 0

        for i in range(len(test_df)):
            sig = signals[i]
            price = closes[i]
            ts = timestamps_test[i]

            if sig > 0 and position == 0:
                position = int(config.starting_cash * config.position_size_pct / price)
                if position < 1:
                    position = 1
                entry_price = price
                entry_side = 1
                cost = position * price * config.commission_per_trade
                slip = position * price * config.slippage_bps / 10000.0
                equity[-1] -= cost + slip
                trades += 1
            elif sig < 0 and position > 0:
                proceeds = position * price
                cost = proceeds * config.commission_per_trade
                slip = proceeds * config.slippage_bps / 10000.0
                pnl = proceeds - entry_price * position - cost - slip
                equity.append(equity[-1] + pnl)
                if pnl > 0:
                    wins += 1
                    gross_profit += pnl
                else:
                    gross_loss += abs(pnl)
                position = 0
                trades += 1
            else:
                if len(equity) > 1:
                    equity.append(equity[-1])
                else:
                    equity.append(equity[-1])

            current_equity = equity[-1]
            if current_equity > peak:
                peak = current_equity
            dd = (peak - current_equity) / peak
            if dd > max_dd:
                max_dd = dd

        if position > 0:
            last_price = closes[-1]
            pnl = position * (last_price - entry_price) - position * last_price * config.commission_per_trade
            equity.append(equity[-1] + pnl)
            if pnl > 0:
                wins += 1
                gross_profit += pnl
            else:
                gross_loss += abs(pnl)
            trades += 1

        if len(equity) < 2:
            equity = [config.starting_cash, config.starting_cash]

        equity_arr = np.array(equity)
        returns = np.diff(equity_arr) / equity_arr[:-1]
        vol = np.std(returns) if len(returns) > 1 else 1e-10
        mean_ret = np.mean(returns) if len(returns) > 1 else 0.0
        sharpe = (mean_ret / vol) * np.sqrt(252) if vol > 1e-10 else 0.0

        total_return = (equity[-1] - config.starting_cash) / config.starting_cash
        win_rate = wins / trades if trades > 0 else 0.0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0

        issues: list[str] = []
        if trades == 0:
            issues.append("no trades in path")
        if sharpe < 0:
            issues.append("negative Sharpe in path")

        results.append(
            BacktestPathResult(
                path_id=split.path_id,
                train_start=split.train_start.isoformat() if split.train_start else None,
                train_end=split.train_end.isoformat() if split.train_end else None,
                test_start=split.test_start.isoformat(),
                test_end=split.test_end.isoformat(),
                total_return=total_return,
                sharpe_ratio=sharpe,
                max_drawdown=-max_dd,
                trade_count=trades,
                win_rate=win_rate,
                profit_factor=profit_factor,
                equity_curve=[float(e) for e in equity],
                passed=sharpe >= 0 and trades >= 3,
                issues=issues,
            )
        )

    return results


def summarize_cpcv_paths(
    paths: list[BacktestPathResult],
    n_paths_tested: int,
    observed_sharpe: float,
    sharpe_std: float,
) -> dict[str, Any]:
    """Summarize CPCV path results.

    Args:
        paths: List of BacktestPathResult objects.
        n_paths_tested: Number of paths tested.
        observed_sharpe: The Sharpe ratio observed in the full backtest.
        sharpe_std: Standard deviation of Sharpe across paths.

    Returns:
        Dictionary with summary statistics.
    """
    if not paths:
        return {
            "n_paths_tested": 0,
            "mean_path_sharpe": 0.0,
            "sharpe_std": 0.0,
            "worst_path_sharpe": 0.0,
            "best_path_sharpe": 0.0,
            "pct_profitable": 0.0,
            "backtest_overfitting_probability": 1.0,
            "deflated_sharpe_ratio": 0.0,
        }

    sharpes = [p.sharpe_ratio for p in paths]
    mean_sharpe = float(np.mean(sharpes))
    std_sharpe = float(np.std(sharpes, ddof=1)) if len(sharpes) > 1 else 0.0
    worst_sharpe = float(np.min(sharpes))
    best_sharpe = float(np.max(sharpes))
    median_sharpe = float(np.median(sharpes))

    n_profitable = sum(1 for p in paths if p.total_return > 0)
    pct_profitable = n_profitable / len(paths) if paths else 0.0

    underperforming = sum(1 for s in sharpes if s < median_sharpe)
    bop_probability = underperforming / len(paths) if paths else 1.0

    sr_with_skew = observed_sharpe if observed_sharpe != 0.0 else mean_sharpe
    deflated_sr = deflated_sharpe_ratio(sr_with_skew, n_paths_tested, sharpe_std)

    return {
        "n_paths_tested": n_paths_tested,
        "mean_path_sharpe": mean_sharpe,
        "sharpe_std": std_sharpe,
        "worst_path_sharpe": worst_sharpe,
        "best_path_sharpe": best_sharpe,
        "median_path_sharpe": median_sharpe,
        "pct_profitable": pct_profitable,
        "backtest_overfitting_probability": bop_probability,
        "deflated_sharpe_ratio": deflated_sr,
        "disclaimer": MANDATORY_DISCLAIMER,
    }


def deflated_sharpe_ratio(
    observed_sharpe: float,
    n_paths: int,
    sharpe_std: float = 0.0,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
) -> float:
    """Compute the Deflated Sharpe Ratio (DSR).

    Adjusts observed Sharpe downward based on the number of independent paths
    tested, penalizing strategies that were selected by picking the best of
    many backtest paths.

    Uses the trial-count penalty: DSR = SR * sqrt(1 - 1/N)

    Args:
        observed_sharpe: Sharpe ratio from the full backtest.
        n_paths: Number of independent paths tested.
        sharpe_std: Standard deviation of Sharpe across paths (unused, for API compat).
        skewness: Estimated skewness (unused, for API compat).
        kurtosis: Kurtosis (unused, for API compat).

    Returns:
        Deflated Sharpe Ratio (adjusted downward for multiple testing).
    """
    if observed_sharpe <= 0:
        return 0.0
    if n_paths <= 1:
        return max(0.0, observed_sharpe)

    n_float = float(n_paths)
    trials_factor = math.sqrt(max(0.0, 1.0 - 1.0 / n_float))

    dsr = observed_sharpe * trials_factor
    return max(0.0, dsr)


def strategy_selection_bias_score(
    observed_sharpe: float,
    mean_path_sharpe: float,
    best_path_sharpe: float,
    n_paths: int,
) -> float:
    """Estimate how much of observed Sharpe is due to best-path selection.

    A high score indicates the observed Sharpe may largely be explained
    by cherry-picking the best backtest path rather than genuine edge.

    Args:
        observed_sharpe: Sharpe from full backtest.
        mean_path_sharpe: Mean Sharpe across CPCV paths.
        best_path_sharpe: Best Sharpe across CPCV paths.
        n_paths: Number of paths tested.

    Returns:
        Bias score between 0 (no bias) and 1 (extreme bias).
    """
    if best_path_sharpe <= mean_path_sharpe:
        return 0.0
    if n_paths < 2:
        return 0.0

    spread = best_path_sharpe - mean_path_sharpe
    advantage = observed_sharpe - mean_path_sharpe

    if advantage <= 0:
        return 1.0

    ratio = advantage / spread if spread > 0 else 0.0

    path_penalty = math.log(float(n_paths)) / float(n_paths)

    bias = ratio * path_penalty
    return min(1.0, max(0.0, bias))


def run_cpcv_validation(
    df: pd.DataFrame,
    config: CPCVConfig,
    observed_sharpe: float = 0.0,
) -> CPCVResult:
    """Run full CPCV validation.

    Args:
        df: DataFrame with timestamp, signal, and price columns.
        config: CPCV configuration.
        observed_sharpe: Observed Sharpe from full backtest (for DSR calculation).

    Returns:
        CPCVResult with all paths and summary statistics.
    """
    splits = generate_cpcv_splits(df, config)
    paths = compute_cpcv_paths(df, splits, config)

    sharpes = [p.sharpe_ratio for p in paths]
    sharpe_std = float(np.std(sharpes, ddof=1)) if len(sharpes) > 1 else 0.0

    summary = summarize_cpcv_paths(paths, len(paths), observed_sharpe, sharpe_std)

    return CPCVResult(
        config=config,
        paths=paths,
        splits=splits,
        created_at=datetime.now(UTC).isoformat(),
        summary=summary,
    )