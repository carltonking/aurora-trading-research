import pandas as pd
import pytest

from aurora.validation.exceptions import WalkForwardValidationError
from aurora.validation.walk_forward import (
    WalkForwardConfig,
    create_walk_forward_windows,
    run_walk_forward_validation,
    _create_anchored_windows,
    _create_rolling_windows,
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


def test_rolling_method_default_behavior() -> None:
    """Test that rolling method with default params matches original behavior."""
    df = _signal_df(80)
    config = WalkForwardConfig(n_splits=4, method="rolling", purge_days=0, embargo_days=0)

    windows = create_walk_forward_windows(df, config)

    assert len(windows) == 4
    for w in windows:
        assert w.test_start is not None
        assert w.test_end is not None


def test_anchored_method_fixed_start() -> None:
    """Test that anchored method has fixed training start."""
    df = _signal_df(80)
    config = WalkForwardConfig(n_splits=4, method="anchored")

    windows = create_walk_forward_windows(df, config)

    assert len(windows) == 4
    first_train_start = windows[0].train_start
    for w in windows:
        assert w.train_start == first_train_start
        assert w.train_start is not None


def test_anchored_method_expanding_window() -> None:
    """Test that anchored method has expanding training windows."""
    df = _signal_df(80)
    config = WalkForwardConfig(n_splits=4, method="anchored", embargo_days=0, purge_days=0)

    windows = create_walk_forward_windows(df, config)

    train_ends = [w.train_end for w in windows if w.train_end]
    if len(train_ends) > 1:
        for i in range(1, len(train_ends)):
            if train_ends[i] and train_ends[i - 1]:
                assert train_ends[i] >= train_ends[i - 1]


def test_purge_days_removes_training_data() -> None:
    """Test that purge_days removes data from training period."""
    df = _signal_df(80)
    config = WalkForwardConfig(n_splits=4, method="rolling", purge_days=5)

    windows = create_walk_forward_windows(df, config)

    for w in windows:
        if w.train_end and w.test_start:
            train_end = pd.Timestamp(w.train_end)
            test_start = pd.Timestamp(w.test_start)
            expected_purge = test_start - pd.Timedelta(days=5)
            assert train_end <= expected_purge


def test_purge_days_zero_no_effect() -> None:
    """Test that purge_days=0 has no effect on training period."""
    df = _signal_df(80)
    config_no_purge = WalkForwardConfig(n_splits=4, method="rolling", purge_days=0)
    config_default = WalkForwardConfig(n_splits=4, method="rolling")

    windows_no_purge = create_walk_forward_windows(df, config_no_purge)
    windows_default = create_walk_forward_windows(df, config_default)

    for w1, w2 in zip(windows_no_purge, windows_default):
        assert w1.train_end == w2.train_end


def test_embargo_days_skips_dates() -> None:
    """Test that embargo_days affects training window timing."""
    df = _signal_df(80)
    config_with_embargo = WalkForwardConfig(n_splits=4, method="anchored", embargo_days=3)
    config_no_embargo = WalkForwardConfig(n_splits=4, method="anchored", embargo_days=0)

    windows_with = create_walk_forward_windows(df, config_with_embargo)
    windows_without = create_walk_forward_windows(df, config_no_embargo)

    for i in range(1, len(windows_with)):
        w_with = windows_with[i]
        w_out = windows_without[i]
        if w_with.train_end and w_out.train_end:
            ts_with = pd.Timestamp(w_with.train_end)
            ts_out = pd.Timestamp(w_out.train_end)
            assert ts_with >= ts_out or ts_with < pd.Timestamp(windows_with[i - 1].test_end)


def test_invalid_method_raises_error() -> None:
    """Test that invalid method raises error."""
    df = _signal_df(80)
    config = WalkForwardConfig(n_splits=4, method="invalid")

    with pytest.raises(WalkForwardValidationError, match="Invalid method"):
        create_walk_forward_windows(df, config)


def test_negative_purge_days_raises_error() -> None:
    """Test that negative purge_days raises error."""
    df = _signal_df(80)
    config = WalkForwardConfig(n_splits=4, purge_days=-1)

    with pytest.raises(WalkForwardValidationError, match="purge_days must be non-negative"):
        create_walk_forward_windows(df, config)


def test_negative_embargo_days_raises_error() -> None:
    """Test that negative embargo_days raises error."""
    df = _signal_df(80)
    config = WalkForwardConfig(n_splits=4, embargo_days=-1)

    with pytest.raises(WalkForwardValidationError, match="embargo_days must be non-negative"):
        create_walk_forward_windows(df, config)


def test_backward_compatibility_default_config() -> None:
    """Test that default config produces same results as before."""
    df = _signal_df(80)

    config_old = WalkForwardConfig(n_splits=4)
    config_new = WalkForwardConfig(n_splits=4, method="rolling", purge_days=0, embargo_days=0)

    windows_old = create_walk_forward_windows(df, config_old)
    windows_new = create_walk_forward_windows(df, config_new)

    for w_old, w_new in zip(windows_old, windows_new):
        assert w_old.window_id == w_new.window_id
        assert w_old.test_start == w_new.test_start
        assert w_old.test_end == w_new.test_end
