"""Technical indicator and feature primitives."""

import numpy as np
import pandas as pd


def simple_return(close: pd.Series, periods: int = 1) -> pd.Series:
    """Calculate percent returns."""
    _validate_positive(periods, "periods")
    return close.copy().pct_change(periods=periods)


def log_return(close: pd.Series, periods: int = 1) -> pd.Series:
    """Calculate log returns."""
    _validate_positive(periods, "periods")
    close_copy = close.copy()
    return np.log(close_copy / close_copy.shift(periods))


def rolling_mean(series: pd.Series, window: int) -> pd.Series:
    """Calculate rolling mean."""
    _validate_positive(window, "window")
    return series.copy().rolling(window=window).mean()


def rolling_std(series: pd.Series, window: int) -> pd.Series:
    """Calculate rolling standard deviation."""
    _validate_positive(window, "window")
    return series.copy().rolling(window=window).std()


def moving_average(close: pd.Series, window: int) -> pd.Series:
    """Calculate simple moving average."""
    return rolling_mean(close, window)


def exponential_moving_average(close: pd.Series, span: int) -> pd.Series:
    """Calculate exponential moving average."""
    _validate_positive(span, "span")
    return close.copy().ewm(span=span, adjust=False).mean()


def rolling_volatility(close: pd.Series, window: int = 20) -> pd.Series:
    """Calculate rolling volatility from simple returns."""
    _validate_positive(window, "window")
    return simple_return(close).rolling(window=window).std()


def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    """Calculate a standard RSI-like oscillator."""
    _validate_positive(window, "window")
    delta = close.copy().diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)
    avg_gain = gains.rolling(window=window).mean()
    avg_loss = losses.rolling(window=window).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    result = 100 - (100 / (1 + rs))
    result = result.mask((avg_loss == 0) & (avg_gain > 0), 100)
    result = result.mask((avg_loss == 0) & (avg_gain == 0), 50)
    return result.clip(lower=0, upper=100)


def macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    """Calculate MACD, signal line, and histogram."""
    _validate_positive(fast, "fast")
    _validate_positive(slow, "slow")
    _validate_positive(signal, "signal")
    fast_ema = exponential_moving_average(close, span=fast)
    slow_ema = exponential_moving_average(close, span=slow)
    macd_line = fast_ema - slow_ema
    signal_line = exponential_moving_average(macd_line, span=signal)
    return pd.DataFrame(
        {
            "macd": macd_line,
            "macd_signal": signal_line,
            "macd_hist": macd_line - signal_line,
        },
        index=close.index,
    )


def true_range(df: pd.DataFrame) -> pd.Series:
    """Calculate true range from high, low, and close columns."""
    required = {"high", "low", "close"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Missing columns for true range: {', '.join(missing)}")

    data = df[["high", "low", "close"]].copy()
    previous_close = data["close"].shift(1)
    ranges = pd.concat(
        [
            data["high"] - data["low"],
            (data["high"] - previous_close).abs(),
            (data["low"] - previous_close).abs(),
        ],
        axis=1,
    )
    return ranges.max(axis=1)


def atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """Calculate average true range."""
    _validate_positive(window, "window")
    return true_range(df).rolling(window=window).mean()


def drawdown(close: pd.Series) -> pd.Series:
    """Calculate current drawdown from cumulative max."""
    close_copy = close.copy()
    return close_copy / close_copy.cummax() - 1


def distance_from_moving_average(close: pd.Series, window: int = 20) -> pd.Series:
    """Calculate percent distance from a moving average."""
    ma = moving_average(close, window)
    return close.copy() / ma - 1


def rolling_high(close: pd.Series, window: int = 20) -> pd.Series:
    """Calculate rolling high."""
    _validate_positive(window, "window")
    return close.copy().rolling(window=window).max()


def rolling_low(close: pd.Series, window: int = 20) -> pd.Series:
    """Calculate rolling low."""
    _validate_positive(window, "window")
    return close.copy().rolling(window=window).min()


def volume_change(volume: pd.Series, periods: int = 1) -> pd.Series:
    """Calculate percent change in volume."""
    _validate_positive(periods, "periods")
    return volume.copy().pct_change(periods=periods)


def _validate_positive(value: int, name: str) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be greater than 0.")


class IndicatorLibrary:
    """Small registry-style wrapper for available indicator names."""

    def list_available(self) -> list[str]:
        """Return available indicator function names."""
        return [
            "simple_return",
            "log_return",
            "moving_average",
            "exponential_moving_average",
            "rolling_volatility",
            "rsi",
            "macd",
            "true_range",
            "atr",
            "drawdown",
            "distance_from_moving_average",
            "rolling_high",
            "rolling_low",
            "volume_change",
        ]
