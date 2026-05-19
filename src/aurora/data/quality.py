"""Market data quality validation."""

from dataclasses import dataclass

import pandas as pd

from aurora.data.normalize import STANDARD_OHLCV_COLUMNS

_REQUIRED_NON_NULL_COLUMNS = ["timestamp", "symbol", "open", "high", "low", "close", "volume"]


@dataclass(frozen=True)
class DataQualityIssue:
    """Single data quality finding."""

    severity: str
    code: str
    message: str
    symbol: str | None = None


@dataclass(frozen=True)
class DataQualityReport:
    """Data quality validation result."""

    ok: bool
    issues: list[DataQualityIssue]
    row_count: int
    symbol_count: int


def validate_ohlcv_quality(df: pd.DataFrame) -> DataQualityReport:
    """Validate a standard OHLCV dataframe."""
    if not isinstance(df, pd.DataFrame):
        raise TypeError("validate_ohlcv_quality expects a pandas DataFrame.")

    df = df.copy()
    issues: list[DataQualityIssue] = []
    row_count = len(df)
    symbol_count = int(df["symbol"].nunique()) if "symbol" in df.columns else 0

    _check_required_columns(df, issues)
    if issues:
        return _report(issues, row_count, symbol_count)

    if df.empty:
        issues.append(DataQualityIssue("error", "empty_dataframe", "Dataframe contains no rows."))
        return _report(issues, row_count, symbol_count)

    _coerce_standard_types(df)
    _check_nulls(df, issues)
    _check_duplicates(df, issues)
    _check_price_relationships(df, issues)
    _check_timestamp_order(df, issues)
    _check_adjusted_close(df, issues)
    _check_zero_volume(df, issues)
    _check_large_moves(df, issues)
    return _report(issues, row_count, symbol_count)


def _check_required_columns(df: pd.DataFrame, issues: list[DataQualityIssue]) -> None:
    missing = [column for column in STANDARD_OHLCV_COLUMNS if column not in df.columns]
    if missing:
        issues.append(
            DataQualityIssue(
                "error",
                "missing_columns",
                f"Missing required columns: {', '.join(missing)}.",
            )
        )


def _coerce_standard_types(df: pd.DataFrame) -> None:
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    for column in ["open", "high", "low", "close", "adjusted_close", "volume"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")


def _check_nulls(df: pd.DataFrame, issues: list[DataQualityIssue]) -> None:
    for column in _REQUIRED_NON_NULL_COLUMNS:
        null_count = int(df[column].isna().sum())
        if null_count:
            issues.append(
                DataQualityIssue(
                    "error",
                    "null_required_value",
                    f"Column {column} contains {null_count} null values.",
                )
            )


def _check_duplicates(df: pd.DataFrame, issues: list[DataQualityIssue]) -> None:
    duplicate_count = int(df.duplicated(subset=["timestamp", "symbol"]).sum())
    if duplicate_count:
        issues.append(
            DataQualityIssue(
                "error",
                "duplicate_symbol_timestamp",
                f"Found {duplicate_count} duplicate timestamp+symbol rows.",
            )
        )


def _check_price_relationships(df: pd.DataFrame, issues: list[DataQualityIssue]) -> None:
    invalid_high_low = df[df["high"] < df["low"]]
    if not invalid_high_low.empty:
        issues.append(
            DataQualityIssue(
                "error",
                "high_less_than_low",
                f"Found {len(invalid_high_low)} rows where high is less than low.",
            )
        )

    for column in ["open", "high", "low", "close"]:
        invalid = df[df[column] <= 0]
        if not invalid.empty:
            issues.append(
                DataQualityIssue(
                    "error",
                    "non_positive_price",
                    f"Column {column} contains {len(invalid)} non-positive values.",
                )
            )

    invalid_volume = df[df["volume"] < 0]
    if not invalid_volume.empty:
        issues.append(
            DataQualityIssue(
                "error",
                "negative_volume",
                f"Found {len(invalid_volume)} rows with negative volume.",
            )
        )


def _check_timestamp_order(df: pd.DataFrame, issues: list[DataQualityIssue]) -> None:
    for symbol, group in df.groupby("symbol", sort=False):
        timestamps = pd.to_datetime(group["timestamp"], errors="coerce")
        if not timestamps.is_monotonic_increasing:
            issues.append(
                DataQualityIssue(
                    "error",
                    "timestamps_not_monotonic",
                    "Timestamps must be monotonic increasing within each symbol.",
                    symbol=str(symbol),
                )
            )


def _check_adjusted_close(df: pd.DataFrame, issues: list[DataQualityIssue]) -> None:
    null_count = int(df["adjusted_close"].isna().sum())
    if null_count:
        issues.append(
            DataQualityIssue(
                "warning",
                "null_adjusted_close",
                f"adjusted_close contains {null_count} null values.",
            )
        )


def _check_zero_volume(df: pd.DataFrame, issues: list[DataQualityIssue]) -> None:
    for symbol, group in df.groupby("symbol", sort=False):
        if group.empty:
            continue
        zero_ratio = float((group["volume"] == 0).mean())
        if zero_ratio > 0.20:
            issues.append(
                DataQualityIssue(
                    "warning",
                    "many_zero_volume_rows",
                    f"Volume is zero for {zero_ratio:.1%} of rows.",
                    symbol=str(symbol),
                )
            )


def _check_large_moves(df: pd.DataFrame, issues: list[DataQualityIssue]) -> None:
    for symbol, group in df.groupby("symbol", sort=False):
        close = pd.to_numeric(group["close"], errors="coerce")
        large_moves = close.pct_change(fill_method=None).abs() > 0.40
        large_move_count = int(large_moves.sum())
        if large_move_count:
            issues.append(
                DataQualityIssue(
                    "warning",
                    "large_close_to_close_move",
                    f"Found {large_move_count} close-to-close moves greater than 40%.",
                    symbol=str(symbol),
                )
            )


def _report(
    issues: list[DataQualityIssue],
    row_count: int,
    symbol_count: int,
) -> DataQualityReport:
    has_errors = any(issue.severity == "error" for issue in issues)
    return DataQualityReport(
        ok=not has_errors,
        issues=issues,
        row_count=row_count,
        symbol_count=symbol_count,
    )


class DataQualityChecker:
    """Compatibility wrapper around OHLCV quality validation."""

    def describe(self) -> str:
        """Return a short description of the component."""
        return "Checks standard OHLCV completeness, continuity, and validity."
