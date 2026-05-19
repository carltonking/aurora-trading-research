"""Walk-forward validation for precomputed research signals."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from aurora.backtesting.engine import BacktestConfig, SimpleLongOnlyBacktester
from aurora.backtesting.exceptions import AuroraBacktestError
from aurora.backtesting.metrics import metrics_to_dict
from aurora.validation.exceptions import WalkForwardValidationError


@dataclass(frozen=True)
class WalkForwardWindow:
    """Chronological walk-forward test window."""

    window_id: str
    train_start: str | None
    train_end: str | None
    test_start: str
    test_end: str


@dataclass(frozen=True)
class WalkForwardConfig:
    """Configuration for walk-forward validation."""

    n_splits: int = 4
    min_test_rows: int = 20
    timestamp_col: str = "timestamp"
    symbol_col: str = "symbol"
    signal_col: str = "signal"
    price_col: str = "adjusted_close"
    starting_cash: float = 100000.0
    position_size_pct: float = 0.05
    max_position_pct: float = 0.10
    commission_per_trade: float = 0.0
    slippage_bps: float = 5.0
    min_total_return: float = 0.0
    max_drawdown_limit: float = -0.25
    min_trade_count: int = 3
    method: str = "rolling"
    purge_days: int = 0
    embargo_days: int = 0


@dataclass(frozen=True)
class WalkForwardWindowResult:
    """Validation result for one walk-forward window."""

    window: WalkForwardWindow
    metrics: dict[str, Any]
    passed: bool
    issues: list[str]


@dataclass(frozen=True)
class WalkForwardResult:
    """Full walk-forward validation result."""

    config: WalkForwardConfig
    windows: list[WalkForwardWindowResult]
    passed: bool
    summary: dict[str, Any]
    created_at: str


def create_walk_forward_windows(
    df: pd.DataFrame,
    config: WalkForwardConfig | None = None,
) -> list[WalkForwardWindow]:
    """Create chronological walk-forward test windows."""
    cfg = config or WalkForwardConfig()
    _validate_window_input(df, cfg)
    timestamps = pd.Series(pd.to_datetime(df[cfg.timestamp_col].dropna().unique())).sort_values()
    timestamps = timestamps.reset_index(drop=True)
    if len(timestamps) < cfg.n_splits:
        raise WalkForwardValidationError(
            f"Need at least {cfg.n_splits} unique timestamps; found {len(timestamps)}."
        )

    windows = []

    if cfg.method == "anchored":
        windows = _create_anchored_windows(timestamps, cfg)
    else:
        windows = _create_rolling_windows(timestamps, cfg)

    return windows


def _create_rolling_windows(timestamps: pd.Series, config: WalkForwardConfig) -> list[WalkForwardWindow]:
    """Create rolling walk-forward windows (existing behavior)."""
    windows = []
    for window_index, index_values in enumerate(_split_indices(len(timestamps), config.n_splits), start=1):
        test_timestamps = timestamps.iloc[index_values]
        test_start = test_timestamps.iloc[0]
        test_end = test_timestamps.iloc[-1]

        train_timestamps = timestamps[timestamps < test_start]

        if config.purge_days > 0:
            purge_start = test_start - pd.Timedelta(days=config.purge_days)
            train_timestamps = train_timestamps[train_timestamps < purge_start]

        windows.append(
            WalkForwardWindow(
                window_id=f"wf_{window_index}",
                train_start=_timestamp_to_str(train_timestamps.iloc[0])
                if not train_timestamps.empty
                else None,
                train_end=_timestamp_to_str(train_timestamps.iloc[-1])
                if not train_timestamps.empty
                else None,
                test_start=_timestamp_to_str(test_start),
                test_end=_timestamp_to_str(test_end),
            )
        )
    return windows


def _create_anchored_windows(timestamps: pd.Series, config: WalkForwardConfig) -> list[WalkForwardWindow]:
    """Create anchored walk-forward windows (fixed start, expanding window)."""
    windows = []
    first_timestamp = timestamps.iloc[0]

    total_length = len(timestamps)
    split_size = total_length // config.n_splits

    for window_index in range(1, config.n_splits + 1):
        test_end_idx = window_index * split_size
        if window_index == config.n_splits:
            test_end_idx = total_length

        test_start_idx = (window_index - 1) * split_size
        test_start = timestamps.iloc[test_start_idx]
        test_end = timestamps.iloc[test_end_idx - 1]

        train_start = first_timestamp

        purge_end = test_start - pd.Timedelta(days=config.purge_days)
        train_end_candidate = purge_end - pd.Timedelta(days=1)

        if config.embargo_days > 0 and window_index > 1:
            prev_test_end = timestamps.iloc[(window_index - 1) * split_size - 1]
            embargo_start = prev_test_end + pd.Timedelta(days=config.embargo_days)
            train_end_candidate = min(train_end_candidate, embargo_start - pd.Timedelta(days=1))

        train_timestamps = timestamps[(timestamps >= train_start) & (timestamps <= train_end_candidate)]

        if len(train_timestamps) < config.min_test_rows:
            train_end = train_end_candidate
            train_timestamps = timestamps[(timestamps >= train_start) & (timestamps <= train_end)]

        windows.append(
            WalkForwardWindow(
                window_id=f"wf_{window_index}",
                train_start=_timestamp_to_str(train_start),
                train_end=_timestamp_to_str(train_timestamps.iloc[-1])
                if not train_timestamps.empty
                else None,
                test_start=_timestamp_to_str(test_start),
                test_end=_timestamp_to_str(test_end),
            )
        )

    return windows


def run_walk_forward_validation(
    signal_df: pd.DataFrame,
    config: WalkForwardConfig | None = None,
) -> WalkForwardResult:
    """Evaluate precomputed signals across chronological windows."""
    cfg = config or WalkForwardConfig()
    _validate_signal_input(signal_df, cfg)
    data = signal_df.copy()
    data[cfg.timestamp_col] = pd.to_datetime(data[cfg.timestamp_col])
    windows = create_walk_forward_windows(data, cfg)
    results = [_evaluate_window(data, window, cfg) for window in windows]
    summary = _build_summary(results)
    passed = bool(results) and all(result.passed for result in results)
    return WalkForwardResult(
        config=cfg,
        windows=results,
        passed=passed,
        summary=summary,
        created_at=datetime.now(UTC).isoformat(),
    )


def _validate_window_input(df: pd.DataFrame, config: WalkForwardConfig) -> None:
    if not isinstance(df, pd.DataFrame):
        raise WalkForwardValidationError("Walk-forward validation expects a pandas DataFrame.")
    if config.n_splits <= 0:
        raise WalkForwardValidationError("n_splits must be greater than 0.")
    if config.timestamp_col not in df.columns:
        raise WalkForwardValidationError(f"Missing timestamp column: {config.timestamp_col}")
    if config.method not in ("rolling", "anchored"):
        raise WalkForwardValidationError(f"Invalid method: {config.method}. Must be 'rolling' or 'anchored'.")
    if config.purge_days < 0:
        raise WalkForwardValidationError("purge_days must be non-negative.")
    if config.embargo_days < 0:
        raise WalkForwardValidationError("embargo_days must be non-negative.")


def _validate_signal_input(df: pd.DataFrame, config: WalkForwardConfig) -> None:
    _validate_window_input(df, config)
    required = {config.timestamp_col, config.symbol_col, config.signal_col, config.price_col}
    missing = sorted(required - set(df.columns))
    if missing:
        raise WalkForwardValidationError(f"Missing signal validation columns: {', '.join(missing)}")
    if df.empty:
        raise WalkForwardValidationError("Signal dataframe is empty.")


def _split_indices(length: int, n_splits: int) -> list[list[int]]:
    base_size, remainder = divmod(length, n_splits)
    splits = []
    start = 0
    for split_index in range(n_splits):
        size = base_size + (1 if split_index < remainder else 0)
        end = start + size
        splits.append(list(range(start, end)))
        start = end
    return splits


def _evaluate_window(
    data: pd.DataFrame,
    window: WalkForwardWindow,
    config: WalkForwardConfig,
) -> WalkForwardWindowResult:
    test_start = pd.Timestamp(window.test_start)
    test_end = pd.Timestamp(window.test_end)
    test_df = data[(data[config.timestamp_col] >= test_start) & (data[config.timestamp_col] <= test_end)]
    issues = []
    if len(test_df) < config.min_test_rows:
        issues.append(f"test row count {len(test_df)} is below minimum {config.min_test_rows}")
        return WalkForwardWindowResult(window=window, metrics={}, passed=False, issues=issues)

    backtest_config = BacktestConfig(
        starting_cash=config.starting_cash,
        position_size_pct=config.position_size_pct,
        max_position_pct=config.max_position_pct,
        commission_per_trade=config.commission_per_trade,
        slippage_bps=config.slippage_bps,
        price_col=config.price_col,
        signal_col=config.signal_col,
        timestamp_col=config.timestamp_col,
        symbol_col=config.symbol_col,
    )
    try:
        backtest_result = SimpleLongOnlyBacktester(backtest_config).run(test_df)
    except AuroraBacktestError as exc:
        issues.append(f"backtest failed: {exc}")
        return WalkForwardWindowResult(window=window, metrics={}, passed=False, issues=issues)

    metrics = metrics_to_dict(backtest_result.metrics)
    issues.extend(_window_metric_issues(metrics, config))
    return WalkForwardWindowResult(
        window=window,
        metrics=metrics,
        passed=not issues,
        issues=issues,
    )


def _window_metric_issues(metrics: dict[str, Any], config: WalkForwardConfig) -> list[str]:
    issues = []
    if float(metrics.get("total_return", 0.0)) < config.min_total_return:
        issues.append(
            f"total_return {metrics.get('total_return')} is below minimum {config.min_total_return}"
        )
    if float(metrics.get("max_drawdown", 0.0)) < config.max_drawdown_limit:
        issues.append(
            f"max_drawdown {metrics.get('max_drawdown')} is below limit {config.max_drawdown_limit}"
        )
    if int(metrics.get("trade_count", 0)) < config.min_trade_count:
        issues.append(
            f"trade_count {metrics.get('trade_count')} is below minimum {config.min_trade_count}"
        )
    return issues


def _build_summary(results: list[WalkForwardWindowResult]) -> dict[str, Any]:
    total_returns = [float(result.metrics["total_return"]) for result in results if "total_return" in result.metrics]
    max_drawdowns = [float(result.metrics["max_drawdown"]) for result in results if "max_drawdown" in result.metrics]
    return {
        "window_count": len(results),
        "passed_window_count": sum(1 for result in results if result.passed),
        "failed_window_count": sum(1 for result in results if not result.passed),
        "average_total_return": _mean_or_none(total_returns),
        "average_max_drawdown": _mean_or_none(max_drawdowns),
        "total_trade_count": sum(int(result.metrics.get("trade_count", 0)) for result in results),
    }


def _mean_or_none(values: list[float]) -> float | None:
    if not values:
        return None
    return float(sum(values) / len(values))


def _timestamp_to_str(timestamp: pd.Timestamp) -> str:
    return pd.Timestamp(timestamp).isoformat()


class WalkForwardValidator:
    """Compatibility wrapper for validation package imports."""

    def describe(self) -> str:
        """Return a short description of the component."""
        return "Evaluates precomputed research signals using walk-forward validation."
