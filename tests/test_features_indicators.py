import numpy as np
import pandas as pd
import pytest

from aurora.features.indicators import (
    atr,
    drawdown,
    log_return,
    macd,
    moving_average,
    rolling_volatility,
    rsi,
    simple_return,
)


def test_simple_return() -> None:
    close = pd.Series([100.0, 110.0, 121.0])

    result = simple_return(close)

    assert np.isnan(result.iloc[0])
    assert result.iloc[1] == pytest.approx(0.10)
    assert result.iloc[2] == pytest.approx(0.10)


def test_log_return() -> None:
    close = pd.Series([100.0, 110.0])

    result = log_return(close)

    assert np.isnan(result.iloc[0])
    assert result.iloc[1] == pytest.approx(np.log(1.10))


def test_moving_average() -> None:
    close = pd.Series([1.0, 2.0, 3.0])

    result = moving_average(close, window=2)

    assert np.isnan(result.iloc[0])
    assert result.iloc[2] == pytest.approx(2.5)


def test_rolling_volatility() -> None:
    close = pd.Series([100.0, 101.0, 102.0, 103.0, 104.0])

    result = rolling_volatility(close, window=2)

    assert len(result) == len(close)
    assert result.notna().sum() > 0


def test_rsi_returns_between_zero_and_100_where_not_null() -> None:
    close = pd.Series([100, 101, 102, 101, 103, 104, 105, 104, 106, 107], dtype=float)

    result = rsi(close, window=3).dropna()

    assert not result.empty
    assert ((result >= 0) & (result <= 100)).all()


def test_macd_returns_required_columns() -> None:
    close = pd.Series(range(1, 40), dtype=float)

    result = macd(close)

    assert list(result.columns) == ["macd", "macd_signal", "macd_hist"]
    assert len(result) == len(close)


def test_atr_returns_series() -> None:
    df = pd.DataFrame(
        {
            "high": [11.0, 12.0, 13.0],
            "low": [9.0, 10.0, 11.0],
            "close": [10.0, 11.0, 12.0],
        }
    )

    result = atr(df, window=2)

    assert isinstance(result, pd.Series)
    assert len(result) == len(df)


def test_drawdown_is_non_positive() -> None:
    close = pd.Series([100.0, 110.0, 105.0, 120.0])

    result = drawdown(close)

    assert (result <= 0).all()


def test_invalid_windows_raise_value_error() -> None:
    close = pd.Series([1.0, 2.0, 3.0])

    with pytest.raises(ValueError):
        moving_average(close, window=0)

    with pytest.raises(ValueError):
        simple_return(close, periods=0)
