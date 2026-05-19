"""Overfitting diagnostics for research validation outputs."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from aurora.validation.walk_forward import WalkForwardResult


@dataclass(frozen=True)
class OverfittingIssue:
    """Single overfitting diagnostic finding."""

    severity: str
    code: str
    message: str


@dataclass(frozen=True)
class OverfittingReport:
    """Overfitting diagnostic report."""

    ok: bool
    issues: list[OverfittingIssue]
    summary: dict[str, Any]
    created_at: str


def diagnose_backtest_overfitting(
    metrics: dict,
    trades: pd.DataFrame | None = None,
    equity_curve: pd.DataFrame | None = None,
    min_trade_count: int = 30,
    max_reasonable_sharpe: float = 5.0,
    max_single_trade_pnl_share: float = 0.50,
) -> OverfittingReport:
    """Diagnose common overfitting risk patterns in a backtest."""
    issues: list[OverfittingIssue] = []
    trade_count = int(metrics.get("trade_count", 0) or 0)
    if trade_count < min_trade_count:
        issues.append(
            OverfittingIssue(
                "error",
                "low_trade_count",
                f"trade_count {trade_count} is below minimum {min_trade_count}.",
            )
        )

    sharpe_ratio = metrics.get("sharpe_ratio")
    if sharpe_ratio is not None and float(sharpe_ratio) > max_reasonable_sharpe:
        issues.append(
            OverfittingIssue(
                "warning",
                "high_sharpe_ratio",
                f"sharpe_ratio {sharpe_ratio} is unusually high.",
            )
        )

    profit_factor = metrics.get("profit_factor")
    if profit_factor is not None and float(profit_factor) > 10:
        issues.append(
            OverfittingIssue(
                "warning",
                "high_profit_factor",
                f"profit_factor {profit_factor} is unusually high.",
            )
        )

    if float(metrics.get("total_return", 0.0) or 0.0) > 0 and float(metrics.get("exposure_pct", 0.0) or 0.0) < 0.02:
        issues.append(
            OverfittingIssue(
                "warning",
                "positive_return_low_exposure",
                "Positive return with very low exposure may indicate concentrated results.",
            )
        )

    _add_trade_concentration_issue(issues, trades, max_single_trade_pnl_share)
    _add_equity_concentration_issue(issues, equity_curve)
    return _build_report(
        issues,
        {
            "trade_count": trade_count,
            "total_return": metrics.get("total_return"),
            "sharpe_ratio": sharpe_ratio,
            "profit_factor": profit_factor,
            "exposure_pct": metrics.get("exposure_pct"),
        },
    )


def diagnose_walk_forward_result(result: WalkForwardResult) -> OverfittingReport:
    """Diagnose overfitting risk in a walk-forward validation result."""
    issues: list[OverfittingIssue] = []
    if not result.passed:
        issues.append(
            OverfittingIssue(
                "error",
                "walk_forward_failed",
                "Walk-forward validation did not pass.",
            )
        )

    window_count = int(result.summary.get("window_count", 0) or 0)
    passed_window_count = int(result.summary.get("passed_window_count", 0) or 0)
    if window_count and (passed_window_count / window_count) < 0.50:
        issues.append(
            OverfittingIssue(
                "warning",
                "low_window_pass_rate",
                "Fewer than 50% of walk-forward windows passed.",
            )
        )

    _add_window_return_concentration_issue(issues, result)
    total_trade_count = int(result.summary.get("total_trade_count", 0) or 0)
    if total_trade_count < 30:
        issues.append(
            OverfittingIssue(
                "warning",
                "low_walk_forward_trade_count",
                f"total_trade_count {total_trade_count} is below 30.",
            )
        )

    return _build_report(issues, dict(result.summary))


def _add_trade_concentration_issue(
    issues: list[OverfittingIssue],
    trades: pd.DataFrame | None,
    max_single_trade_pnl_share: float,
) -> None:
    if trades is None or trades.empty or "net_pnl" not in trades.columns:
        return
    pnl = pd.to_numeric(trades["net_pnl"], errors="coerce").dropna()
    positive_pnl = pnl[pnl > 0]
    total_positive = float(positive_pnl.sum())
    if total_positive <= 0 or positive_pnl.empty:
        return
    largest_share = float(positive_pnl.max() / total_positive)
    if largest_share > max_single_trade_pnl_share:
        issues.append(
            OverfittingIssue(
                "warning",
                "single_trade_pnl_concentration",
                f"Largest winning trade accounts for {largest_share:.1%} of total positive PnL.",
            )
        )


def _add_equity_concentration_issue(
    issues: list[OverfittingIssue],
    equity_curve: pd.DataFrame | None,
) -> None:
    if equity_curve is None or equity_curve.empty or "equity" not in equity_curve.columns:
        return
    returns = pd.to_numeric(equity_curve["equity"], errors="coerce").pct_change().dropna()
    positive_returns = returns[returns > 0]
    total_positive = float(positive_returns.sum())
    if total_positive <= 0 or positive_returns.empty:
        return
    largest_share = float(positive_returns.max() / total_positive)
    if largest_share > 0.50:
        issues.append(
            OverfittingIssue(
                "warning",
                "single_period_return_concentration",
                f"Largest positive equity period accounts for {largest_share:.1%} of positive returns.",
            )
        )


def _add_window_return_concentration_issue(
    issues: list[OverfittingIssue],
    result: WalkForwardResult,
) -> None:
    returns = [
        float(window.metrics["total_return"])
        for window in result.windows
        if window.metrics.get("total_return") is not None and float(window.metrics["total_return"]) > 0
    ]
    total_positive = sum(returns)
    if total_positive <= 0 or not returns:
        return
    largest_share = max(returns) / total_positive
    if largest_share > 0.60:
        issues.append(
            OverfittingIssue(
                "warning",
                "single_window_return_concentration",
                f"Largest positive window accounts for {largest_share:.1%} of positive window returns.",
            )
        )


def _build_report(issues: list[OverfittingIssue], summary: dict[str, Any]) -> OverfittingReport:
    has_error = any(issue.severity == "error" for issue in issues)
    return OverfittingReport(
        ok=not has_error,
        issues=issues,
        summary=summary,
        created_at=datetime.now(UTC).isoformat(),
    )
