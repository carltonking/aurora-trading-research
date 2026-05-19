import pandas as pd

from aurora.strategies.signals import (
    SIGNAL_COLUMN,
    SIGNAL_LONG,
    SIGNAL_REASON_COLUMN,
    empty_signal_frame,
    summarize_signals,
)


def test_empty_signal_frame_adds_required_columns() -> None:
    df = pd.DataFrame({"symbol": ["AAPL", "MSFT"]})

    result = empty_signal_frame(df, "strategy_one")

    assert result["strategy_id"].tolist() == ["strategy_one", "strategy_one"]
    assert result[SIGNAL_COLUMN].tolist() == [0, 0]
    assert result[SIGNAL_REASON_COLUMN].tolist() == ["flat", "flat"]


def test_summarize_signals_counts_long_and_flat() -> None:
    df = empty_signal_frame(pd.DataFrame({"symbol": ["AAPL", "AAPL", "AAPL"]}), "strategy_one")
    df.loc[0, SIGNAL_COLUMN] = SIGNAL_LONG

    result = summarize_signals(df, "strategy_one")

    assert result.row_count == 3
    assert result.signal_count == 1
    assert result.long_count == 1
    assert result.flat_count == 2
