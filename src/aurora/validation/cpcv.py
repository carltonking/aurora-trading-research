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

from aurora.validation.path_analysis import (
    deflated_sharpe_ratio as _canonical_deflated_sharpe_ratio,
)


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
            test_indices_raw.update(groups[gi].tolist())

        train_indices_raw: set[int] = set()
        for gi in range(config.n_splits):
            if gi not in test_group_indices:
                train_indices_raw.update(groups[gi].tolist())

        test_sorted = sorted(test_indices_raw)
        test_dates = timestamps[test_sorted]
        test_start = pd.Timestamp(test_dates[0])
        test_end = pd.Timestamp(test_dates[-1])

        # The test set can span several non-contiguous groups (e.g. test {0,2}
        # leaves train {1} in the middle). Purge/embargo must be applied around
        # EACH contiguous test block independently, not around the overall
        # [min,max] envelope — otherwise legitimate training data between test
        # blocks is silently swallowed.
        test_blocks = [
            (pd.Timestamp(timestamps[groups[gi][0]]), pd.Timestamp(timestamps[groups[gi][-1]]))
            for gi in test_group_indices
        ]

        def _is_purged_or_embargoed(ts: pd.Timestamp) -> bool:
            for block_start, block_end in test_blocks:
                # Purge: a training observation labelled at time ``ts`` carries
                # information over its label window [ts, ts + purge_days]. Remove
                # it if that window overlaps the test block on EITHER side — i.e.
                # the training label ends inside/after the test block starts AND
                # the training observation begins at/before the test block ends.
                label_end = ts + pd.Timedelta(days=purge_buffer)
                overlaps_test = (label_end >= block_start) and (ts <= block_end)
                if overlaps_test:
                    return True
                # Embargo: also drop training observations that fall within the
                # embargo window immediately AFTER the test block (serial
                # correlation leaks forward from test into subsequent training).
                if block_end < ts <= block_end + pd.Timedelta(days=embargo_buffer):
                    return True
            return False

        train_indices: list[int] = []
        for idx in sorted(train_indices_raw):
            ts = pd.Timestamp(timestamps[idx])
            if _is_purged_or_embargoed(ts):
                continue
            train_indices.append(idx)

        if train_indices:
            kept_dates = timestamps[train_indices]
            train_start = pd.Timestamp(kept_dates.min())
            train_end = pd.Timestamp(kept_dates.max())
        else:
            train_start = None
            train_end = None

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

        # Mark-to-market accounting. We track cash and a share ``position`` and
        # append exactly ONE equity point per bar (plus the starting point), so
        # the equity curve is always aligned with the test bars. The previous
        # implementation mutated equity[-1] in place on buys while appending on
        # sells/holds, producing a misaligned, double-counted return series fed
        # to the Sharpe calculation.
        cash = float(config.starting_cash)
        position = 0  # shares held
        equity = [cash]
        trades = 0
        wins = 0
        gross_profit = 0.0
        gross_loss = 0.0
        peak = cash
        max_dd = 0.0

        signals = test_df[config.signal_col].values
        closes = test_df[config.price_col].values

        entry_cost_basis = 0.0  # cash spent to open the current position

        for i in range(len(test_df)):
            sig = signals[i]
            price = float(closes[i])

            if sig > 0 and position == 0:
                shares = int(config.starting_cash * config.position_size_pct / price)
                if shares < 1:
                    shares = 1
                gross = shares * price
                cost = gross * config.commission_per_trade
                slip = gross * config.slippage_bps / 10000.0
                cash -= gross + cost + slip
                entry_cost_basis = gross + cost + slip
                position = shares
                trades += 1
            elif sig < 0 and position > 0:
                proceeds = position * price
                cost = proceeds * config.commission_per_trade
                slip = proceeds * config.slippage_bps / 10000.0
                net_proceeds = proceeds - cost - slip
                cash += net_proceeds
                pnl = net_proceeds - entry_cost_basis
                if pnl > 0:
                    wins += 1
                    gross_profit += pnl
                else:
                    gross_loss += abs(pnl)
                position = 0
                entry_cost_basis = 0.0
                trades += 1

            # Mark to market: equity = cash + value of any open position.
            current_equity = cash + position * price
            equity.append(current_equity)

            if current_equity > peak:
                peak = current_equity
            dd = (peak - current_equity) / peak if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd

        # Close any open position at the final bar for a count, but the
        # mark-to-market equity already reflects its value, so do not append a
        # spurious extra equity point here.
        if position > 0:
            last_price = float(closes[-1])
            proceeds = position * last_price
            cost = proceeds * config.commission_per_trade
            net_proceeds = proceeds - cost
            pnl = net_proceeds - entry_cost_basis
            if pnl > 0:
                wins += 1
                gross_profit += pnl
            else:
                gross_loss += abs(pnl)
            trades += 1

        if len(equity) < 2:
            equity = [config.starting_cash, config.starting_cash]

        equity_arr = np.array(equity)
        base = equity_arr[:-1]
        with np.errstate(divide="ignore", invalid="ignore"):
            returns = np.diff(equity_arr) / np.where(base == 0.0, np.nan, base)
        returns = returns[np.isfinite(returns)]
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


def probability_of_backtest_overfitting(
    performance_matrix: np.ndarray,
    n_blocks: int = 10,
) -> float | None:
    """Probability of Backtest Overfitting (PBO) via CSCV.

    Implements Bailey & López de Prado's Combinatorially Symmetric
    Cross-Validation (CSCV). PBO is only well-defined when there is a *grid of
    candidate configurations* to choose among — it measures the probability
    that the configuration selected as best in-sample (IS) ranks below the
    median out-of-sample (OOS). With a single strategy there is nothing to
    select between, so this returns ``None``.

    Algorithm:
      1. Partition the T observations (rows) into ``S`` even, contiguous
         submatrices (blocks).
      2. For each of the C(S, S/2) ways to choose S/2 blocks as IS (the
         complement is OOS), evaluate every configuration's IS and OOS Sharpe.
      3. Pick n* = argmax of IS Sharpe. Compute its OOS rank, normalized to
         omega_bar in (0, 1), and the logit lambda = ln(omega_bar / (1 -
         omega_bar)).
      4. PBO = fraction of combinations with lambda <= 0 (i.e. the IS-best
         config landed at or below the OOS median).

    Args:
        performance_matrix: Array of shape (T, C) — per-observation returns for
            each of C candidate configurations. Requires C >= 2.
        n_blocks: Number of even submatrices S (must be even and >= 2).

    Returns:
        PBO in [0, 1], or ``None`` if PBO is not well-defined (fewer than two
        configurations, or insufficient data to form the blocks).
    """
    perf = np.asarray(performance_matrix, dtype=float)
    if perf.ndim != 2:
        return None
    n_obs, n_configs = perf.shape
    # PBO requires a choice among multiple configurations.
    if n_configs < 2:
        return None

    s = int(n_blocks)
    if s % 2 != 0:
        s -= 1
    if s < 2:
        return None
    # Need at least a couple of observations per block.
    if n_obs < s * 2:
        s = max(2, (n_obs // 2) * 2)
        if s < 2 or n_obs < s:
            return None

    blocks = np.array_split(np.arange(n_obs), s)
    block_ids = list(range(s))

    def _sharpe(matrix: np.ndarray) -> np.ndarray:
        mean = matrix.mean(axis=0)
        std = matrix.std(axis=0, ddof=1) if matrix.shape[0] > 1 else np.zeros(matrix.shape[1])
        out = np.zeros_like(mean)
        nz = std > 1e-12
        out[nz] = mean[nz] / std[nz]
        return out

    lambdas: list[float] = []
    for is_combo in combinations(block_ids, s // 2):
        is_set = set(is_combo)
        is_rows = np.concatenate([blocks[b] for b in block_ids if b in is_set])
        oos_rows = np.concatenate([blocks[b] for b in block_ids if b not in is_set])
        if len(is_rows) < 2 or len(oos_rows) < 2:
            continue

        is_sharpe = _sharpe(perf[is_rows, :])
        oos_sharpe = _sharpe(perf[oos_rows, :])

        best_is = int(np.argmax(is_sharpe))
        # OOS rank of the IS-best config among all configs (1 = worst).
        order = np.argsort(oos_sharpe, kind="mergesort")
        ranks = np.empty(n_configs, dtype=float)
        ranks[order] = np.arange(1, n_configs + 1)
        # Normalize relative rank into (0, 1), avoiding the open endpoints.
        omega_bar = ranks[best_is] / (n_configs + 1)
        omega_bar = min(max(omega_bar, 1e-9), 1.0 - 1e-9)
        lam = math.log(omega_bar / (1.0 - omega_bar))
        lambdas.append(lam)

    if not lambdas:
        return None

    n_overfit = sum(1 for lam in lambdas if lam <= 0.0)
    return float(n_overfit / len(lambdas))


def summarize_cpcv_paths(
    paths: list[BacktestPathResult],
    n_paths_tested: int,
    observed_sharpe: float,
    sharpe_std: float,
    return_skew: float = 0.0,
    return_kurtosis: float = 3.0,
    n_observations: int = 252,
    pbo: float | None = None,
) -> dict[str, Any]:
    """Summarize CPCV path results.

    Args:
        paths: List of BacktestPathResult objects.
        n_paths_tested: Number of paths tested (= number of trials for DSR).
        observed_sharpe: The Sharpe ratio observed in the full backtest.
        sharpe_std: Standard deviation of Sharpe across paths (the trial-Sharpe
            dispersion that feeds the expected-maximum-Sharpe benchmark).
        return_skew: Skewness of the pooled OOS return series (for DSR).
        return_kurtosis: Kurtosis of the pooled OOS return series (for DSR).
        n_observations: Number of return observations T behind the Sharpe.
        pbo: Probability of Backtest Overfitting from CSCV, or ``None`` when not
            well-defined (single configuration). Reported as
            ``backtest_overfitting_probability``.

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
            "backtest_overfitting_probability": pbo,
            "pbo_note": (
                "PBO (CSCV) requires a grid of candidate configurations; it is "
                "not well-defined for a single strategy and is reported as null."
            ),
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

    # DSR uses the dispersion of the trial (path) Sharpe estimates as sigma_SR;
    # fall back to the precomputed sharpe_std if needed.
    sigma_sr = std_sharpe if std_sharpe > 0.0 else sharpe_std
    sr_for_dsr = observed_sharpe if observed_sharpe != 0.0 else mean_sharpe
    deflated_sr = deflated_sharpe_ratio(
        sr_for_dsr,
        n_paths_tested,
        sharpe_std=sigma_sr,
        skewness=return_skew,
        kurtosis=return_kurtosis,
        n_observations=n_observations,
    )

    pbo_note = (
        "PBO (CSCV) requires a grid of candidate configurations; it is not "
        "well-defined for a single strategy and is reported as null."
        if pbo is None
        else "PBO computed via Combinatorially Symmetric Cross-Validation (CSCV)."
    )

    return {
        "n_paths_tested": n_paths_tested,
        "mean_path_sharpe": mean_sharpe,
        "sharpe_std": std_sharpe,
        "worst_path_sharpe": worst_sharpe,
        "best_path_sharpe": best_sharpe,
        "median_path_sharpe": median_sharpe,
        "pct_profitable": pct_profitable,
        "backtest_overfitting_probability": pbo,
        "pbo_note": pbo_note,
        "deflated_sharpe_ratio": deflated_sr,
        "disclaimer": MANDATORY_DISCLAIMER,
    }


def deflated_sharpe_ratio(
    observed_sharpe: float,
    n_paths: int,
    sharpe_std: float = 0.0,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
    n_observations: int = 252,
) -> float:
    """Compute the Deflated Sharpe Ratio (DSR) — López de Prado (2014).

    This is a thin wrapper around the canonical implementation in
    ``aurora.validation.path_analysis.deflated_sharpe_ratio`` so that CPCV and
    path-analysis callers share one, correct definition. The DSR is the
    probability (in [0, 1]) that the observed Sharpe exceeds the
    expected-maximum Sharpe achievable by chance across ``n_paths`` trials,
    adjusted for the skew and kurtosis of the return series. It decreases as the
    number of trials grows (multiple-testing penalty) and increases with a
    higher observed Sharpe. See the canonical docstring for the full formula.

    Args:
        observed_sharpe: Observed Sharpe ratio.
        n_paths: Number of trials / CPCV paths tested.
        sharpe_std: Standard deviation of the trial Sharpe estimates.
        skewness: Skewness of the return series.
        kurtosis: Kurtosis of the return series (3.0 for normal).
        n_observations: Number of return observations T.

    Returns:
        Deflated Sharpe Ratio as a probability in [0, 1].
    """
    return _canonical_deflated_sharpe_ratio(
        observed_sharpe=observed_sharpe,
        n_paths=n_paths,
        sharpe_std=sharpe_std,
        skewness=skewness,
        kurtosis=kurtosis,
        n_observations=n_observations,
    )


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

    # Pool the per-path return series (from each path's equity curve) so the DSR
    # can estimate the skew/kurtosis of the return distribution and the number
    # of observations T. These higher moments are required for a correct DSR;
    # the old code ignored them.
    pooled_returns: list[float] = []
    for p in paths:
        eq = np.asarray(p.equity_curve, dtype=float)
        if len(eq) > 1:
            base = eq[:-1]
            with np.errstate(divide="ignore", invalid="ignore"):
                rets = np.diff(eq) / np.where(base == 0.0, np.nan, base)
            rets = rets[np.isfinite(rets)]
            pooled_returns.extend(rets.tolist())

    if len(pooled_returns) >= 3:
        from scipy import stats as _scipy_stats

        ret_arr = np.asarray(pooled_returns, dtype=float)
        return_skew = float(_scipy_stats.skew(ret_arr))
        # Pearson kurtosis (fisher=False): 3.0 for a normal distribution, which
        # is what the DSR variance term expects.
        return_kurtosis = float(_scipy_stats.kurtosis(ret_arr, fisher=False))
        n_observations = int(len(ret_arr))
    else:
        return_skew = 0.0
        return_kurtosis = 3.0
        n_observations = 252

    # PBO via CSCV is undefined for a single strategy configuration (AURORA's
    # CPCV evaluates one strategy across paths, not a grid). Report it as None
    # rather than fabricating a meaningless ~0.5.
    summary = summarize_cpcv_paths(
        paths,
        len(paths),
        observed_sharpe,
        sharpe_std,
        return_skew=return_skew,
        return_kurtosis=return_kurtosis,
        n_observations=n_observations,
        pbo=None,
    )

    return CPCVResult(
        config=config,
        paths=paths,
        splits=splits,
        created_at=datetime.now(UTC).isoformat(),
        summary=summary,
    )