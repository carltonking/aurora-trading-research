import pandas as pd

from aurora.validation.overfitting import (
    diagnose_backtest_overfitting,
    diagnose_walk_forward_result,
)
from aurora.validation.walk_forward import (
    WalkForwardConfig,
    WalkForwardResult,
    WalkForwardWindow,
    WalkForwardWindowResult,
)


def test_low_trade_count_produces_error_and_not_ok() -> None:
    report = diagnose_backtest_overfitting({"trade_count": 2, "total_return": 0.1})

    assert report.ok is False
    assert any(issue.code == "low_trade_count" and issue.severity == "error" for issue in report.issues)


def test_high_sharpe_produces_warning_but_can_remain_ok() -> None:
    report = diagnose_backtest_overfitting(
        {"trade_count": 40, "sharpe_ratio": 6.5, "total_return": 0.1, "exposure_pct": 0.5}
    )

    assert report.ok is True
    assert any(issue.code == "high_sharpe_ratio" for issue in report.issues)


def test_single_trade_concentration_produces_warning() -> None:
    trades = pd.DataFrame({"net_pnl": [100.0, 2.0, 1.0]})

    report = diagnose_backtest_overfitting(
        {"trade_count": 40, "total_return": 0.1, "exposure_pct": 0.5},
        trades=trades,
    )

    assert report.ok is True
    assert any(issue.code == "single_trade_pnl_concentration" for issue in report.issues)


def test_failed_walk_forward_result_produces_error() -> None:
    window = WalkForwardWindow(
        window_id="wf_1",
        train_start=None,
        train_end=None,
        test_start="2024-01-01T00:00:00",
        test_end="2024-01-20T00:00:00",
    )
    result = WalkForwardResult(
        config=WalkForwardConfig(),
        windows=[
            WalkForwardWindowResult(
                window=window,
                metrics={"total_return": -0.01, "max_drawdown": -0.02, "trade_count": 1},
                passed=False,
                issues=["failed"],
            )
        ],
        passed=False,
        summary={
            "window_count": 1,
            "passed_window_count": 0,
            "failed_window_count": 1,
            "average_total_return": -0.01,
            "average_max_drawdown": -0.02,
            "total_trade_count": 1,
        },
        created_at="2026-01-01T00:00:00+00:00",
    )

    report = diagnose_walk_forward_result(result)

    assert report.ok is False
    assert any(issue.code == "walk_forward_failed" for issue in report.issues)
