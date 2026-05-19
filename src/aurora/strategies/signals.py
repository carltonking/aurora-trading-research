"""Signal dataframe helpers."""

from datetime import UTC, datetime

import pandas as pd

from aurora.strategies.base import SignalResult

SIGNAL_LONG = 1
SIGNAL_FLAT = 0
SIGNAL_COLUMN = "signal"
SIGNAL_REASON_COLUMN = "signal_reason"


def empty_signal_frame(df: pd.DataFrame, strategy_id: str) -> pd.DataFrame:
    """Return a copy with default flat research signals."""
    output = df.copy()
    output["strategy_id"] = strategy_id
    output[SIGNAL_COLUMN] = SIGNAL_FLAT
    output[SIGNAL_REASON_COLUMN] = "flat"
    return output


def summarize_signals(df: pd.DataFrame, strategy_id: str) -> SignalResult:
    """Summarize generated signal counts."""
    long_count = int((df[SIGNAL_COLUMN] == SIGNAL_LONG).sum())
    flat_count = int((df[SIGNAL_COLUMN] == SIGNAL_FLAT).sum())
    return SignalResult(
        strategy_id=strategy_id,
        row_count=len(df),
        signal_count=int((df[SIGNAL_COLUMN] != SIGNAL_FLAT).sum()),
        long_count=long_count,
        flat_count=flat_count,
        created_at=datetime.now(UTC).isoformat(),
    )
