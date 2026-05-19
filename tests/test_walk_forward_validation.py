import pandas as pd
import pytest

from aurora.validation.exceptions import WalkForwardValidationError
from aurora.validation.walk_forward import (
    WalkForwardConfig,
    create_walk_forward_windows,
    run_walk_forward_validation,
)


def _signal_df(rows: int = 80) -> pd.DataFrame:
    pattern = [1, 1, 0, 0]
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=rows, freq="D"),
            "symbol": ["AAPL"] * rows,
            "adjusted_close": [100.0 + i for i in range(rows)],
            "signal": [pattern[i % len(pattern)] for i in range(rows)],
        }
    )


def test_create_walk_forward_windows_creates_expected_number() -> None:
    windows = create_walk_forward_windows(
        _signal_df(),
        WalkForwardConfig(n_splits=4, min_test_rows=10),
    )

    assert len(windows) == 4
    assert windows[0].train_start is None
    assert windows[1].train_start is not None
    assert windows[0].test_start < windows[0].test_end


def test_run_walk_forward_validation_returns_result_with_summary() -> None:
    result = run_walk_forward_validation(
        _signal_df(),
        WalkForwardConfig(n_splits=4, min_test_rows=10, min_trade_count=1),
    )

    assert result.summary["window_count"] == 4
    assert result.summary["passed_window_count"] == 4
    assert result.summary["failed_window_count"] == 0
    assert result.summary["total_trade_count"] > 0
    assert result.passed is True


def test_validation_fails_when_min_trade_count_is_too_high() -> None:
    result = run_walk_forward_validation(
        _signal_df(),
        WalkForwardConfig(n_splits=4, min_test_rows=10, min_trade_count=100),
    )

    assert result.passed is False
    assert result.summary["failed_window_count"] == 4
    assert any("trade_count" in issue for window in result.windows for issue in window.issues)


def test_missing_timestamp_raises_walk_forward_validation_error() -> None:
    with pytest.raises(WalkForwardValidationError):
        create_walk_forward_windows(pd.DataFrame({"signal": [1, 0]}))
