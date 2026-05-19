import pandas as pd
import pytest

from aurora.backtesting.engine import BacktestConfig, BacktestResult, SimpleLongOnlyBacktester
from aurora.backtesting.exceptions import BacktestInputError


def _signals(
    symbols: list[str] | None = None,
    prices: list[float] | None = None,
    signals: list[int] | None = None,
) -> pd.DataFrame:
    symbols = symbols or ["AAPL"]
    prices = prices or [100.0, 101.0, 102.0, 103.0]
    signals = signals or [0, 1, 1, 0]
    rows = []
    for symbol_index, symbol in enumerate(symbols):
        for i, price in enumerate(prices):
            rows.append(
                {
                    "timestamp": pd.Timestamp("2024-01-01") + pd.Timedelta(days=i),
                    "symbol": symbol,
                    "adjusted_close": price + symbol_index,
                    "signal": signals[i],
                }
            )
    return pd.DataFrame(rows)


def test_invalid_missing_columns_raises_backtest_input_error() -> None:
    with pytest.raises(BacktestInputError):
        SimpleLongOnlyBacktester().run(pd.DataFrame({"symbol": ["AAPL"]}))


def test_simple_single_symbol_sequence_creates_closed_trade() -> None:
    result = SimpleLongOnlyBacktester(
        BacktestConfig(starting_cash=10000.0, slippage_bps=0.0)
    ).run(_signals())

    assert len(result.trades) == 1
    assert result.trades.loc[0, "symbol"] == "AAPL"
    assert result.trades.loc[0, "exit_reason"] == "signal_flat"
    assert result.trades.loc[0, "gross_pnl"] > 0
    assert result.metrics.trade_count == 1


def test_open_position_closes_at_end_of_data() -> None:
    result = SimpleLongOnlyBacktester(
        BacktestConfig(starting_cash=10000.0, slippage_bps=0.0)
    ).run(_signals(signals=[1, 1, 1, 1]))

    assert len(result.trades) == 1
    assert result.trades.loc[0, "exit_reason"] == "end_of_data"
    assert result.equity_curve.iloc[-1]["market_value"] == 0.0


def test_no_margin_behavior_skips_entry_if_insufficient_cash() -> None:
    result = SimpleLongOnlyBacktester(
        BacktestConfig(starting_cash=10.0, commission_per_trade=20.0)
    ).run(_signals(signals=[1, 1, 0, 0]))

    assert result.trades.empty
    assert result.metrics.trade_count == 0
    assert result.metrics.final_equity == pytest.approx(10.0)


def test_multi_symbol_input_produces_equity_curve_and_trades() -> None:
    result = SimpleLongOnlyBacktester(
        BacktestConfig(starting_cash=10000.0, slippage_bps=0.0)
    ).run(_signals(symbols=["AAPL", "MSFT"]))

    assert len(result.equity_curve) == 4
    assert len(result.trades) == 2
    assert set(result.trades["symbol"]) == {"AAPL", "MSFT"}


def test_output_contains_metrics_equity_trades_and_signals() -> None:
    signal_df = _signals()

    result = SimpleLongOnlyBacktester().run(signal_df)

    assert isinstance(result, BacktestResult)
    assert not result.equity_curve.empty
    assert "equity" in result.equity_curve.columns
    assert "trade_id" in result.trades.columns
    assert result.signals.equals(signal_df)
