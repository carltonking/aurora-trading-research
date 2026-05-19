"""Validation package."""

from aurora.validation.overfitting import (
    OverfittingIssue,
    OverfittingReport,
    diagnose_backtest_overfitting,
    diagnose_walk_forward_result,
)
from aurora.validation.report import (
    load_validation_report,
    overfitting_report_to_dict,
    save_validation_report,
    walk_forward_result_to_dict,
)
from aurora.validation.walk_forward import (
    WalkForwardConfig,
    WalkForwardResult,
    WalkForwardWindow,
    WalkForwardWindowResult,
    create_walk_forward_windows,
    run_walk_forward_validation,
)

__all__ = [
    "OverfittingIssue",
    "OverfittingReport",
    "WalkForwardConfig",
    "WalkForwardResult",
    "WalkForwardWindow",
    "WalkForwardWindowResult",
    "create_walk_forward_windows",
    "diagnose_backtest_overfitting",
    "diagnose_walk_forward_result",
    "load_validation_report",
    "overfitting_report_to_dict",
    "run_walk_forward_validation",
    "save_validation_report",
    "walk_forward_result_to_dict",
]
