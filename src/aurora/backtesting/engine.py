"""Simple long-only research backtesting engine."""

from dataclasses import dataclass
from typing import Any

import pandas as pd

from aurora.backtesting.exceptions import BacktestInputError
from aurora.backtesting.metrics import BacktestMetrics, calculate_equity_curve_metrics
from aurora.backtesting.trades import Position, Trade, trades_to_dataframe


@dataclass(frozen=True)
class BacktestConfig:
    """Configuration for the simple long-only backtester."""

    starting_cash: float = 100000.0
    position_size_pct: float = 0.05
    max_position_pct: float = 0.10
    commission_per_trade: float = 0.0
    slippage_bps: float = 5.0
    price_col: str = "adjusted_close"
    signal_col: str = "signal"
    timestamp_col: str = "timestamp"
    symbol_col: str = "symbol"
    periods_per_year: int = 252


@dataclass(frozen=True)
class BacktestResult:
    """Complete result from a research backtest."""

    config: BacktestConfig
    metrics: BacktestMetrics
    equity_curve: pd.DataFrame
    trades: pd.DataFrame
    signals: pd.DataFrame


class SimpleLongOnlyBacktester:
    """Transparent long-only signal evaluator."""

    def __init__(self, config: BacktestConfig | None = None) -> None:
        self.config = config or BacktestConfig()

    def run(self, signal_df: pd.DataFrame) -> BacktestResult:
        """Run the long-only backtest."""
        self._validate_input(signal_df)
        data = signal_df.copy()
        data[self.config.timestamp_col] = pd.to_datetime(data[self.config.timestamp_col])
        data = data.sort_values([self.config.timestamp_col, self.config.symbol_col]).reset_index(drop=True)

        cash = float(self.config.starting_cash)
        positions: dict[str, Position] = {}
        previous_signals: dict[str, int] = {}
        latest_prices: dict[str, float] = {}
        trades: list[Trade] = []
        equity_rows: list[dict[str, Any]] = []
        trade_counter = 1

        for timestamp, rows in data.groupby(self.config.timestamp_col, sort=True):
            latest_prices.update(self._prices_for_rows(rows))
            cash, trade_counter = self._process_exits(
                rows=rows,
                positions=positions,
                previous_signals=previous_signals,
                cash=cash,
                trades=trades,
                trade_counter=trade_counter,
                timestamp=timestamp,
            )
            cash = self._process_entries(
                rows=rows,
                positions=positions,
                previous_signals=previous_signals,
                cash=cash,
                latest_prices=latest_prices,
            )
            equity = cash + self._market_value(positions, latest_prices)
            market_value = equity - cash
            equity_rows.append(
                {
                    "timestamp": timestamp,
                    "equity": equity,
                    "cash": cash,
                    "market_value": market_value,
                    "exposure": market_value / equity if equity > 0 else 0.0,
                }
            )
            self._update_previous_signals(rows, previous_signals)
            for position in positions.values():
                position.bars_held += 1

        if positions:
            cash, trade_counter = self._close_end_of_data(
                positions=positions,
                latest_prices=latest_prices,
                cash=cash,
                trades=trades,
                trade_counter=trade_counter,
                timestamp=data[self.config.timestamp_col].iloc[-1],
            )
            equity_rows[-1]["cash"] = cash
            equity_rows[-1]["market_value"] = 0.0
            equity_rows[-1]["equity"] = cash
            equity_rows[-1]["exposure"] = 0.0

        equity_curve = pd.DataFrame(equity_rows)
        trades_df = trades_to_dataframe(trades)
        metrics = calculate_equity_curve_metrics(
            equity_curve,
            trades_df,
            starting_cash=self.config.starting_cash,
            periods_per_year=self.config.periods_per_year,
        )
        return BacktestResult(
            config=self.config,
            metrics=metrics,
            equity_curve=equity_curve,
            trades=trades_df,
            signals=signal_df.copy(),
        )

    def _validate_input(self, signal_df: pd.DataFrame) -> None:
        if not isinstance(signal_df, pd.DataFrame):
            raise BacktestInputError("Backtester expects a pandas DataFrame.")
        required = {
            self.config.timestamp_col,
            self.config.symbol_col,
            self.config.price_col,
            self.config.signal_col,
        }
        missing = sorted(required - set(signal_df.columns))
        if missing:
            raise BacktestInputError(f"Missing required backtest columns: {', '.join(missing)}")
        if signal_df.empty:
            raise BacktestInputError("Signal dataframe is empty.")
        if self.config.starting_cash <= 0:
            raise BacktestInputError("starting_cash must be greater than 0.")
        if self.config.position_size_pct <= 0 or self.config.max_position_pct <= 0:
            raise BacktestInputError("position sizing percentages must be greater than 0.")

    def _process_exits(
        self,
        rows: pd.DataFrame,
        positions: dict[str, Position],
        previous_signals: dict[str, int],
        cash: float,
        trades: list[Trade],
        trade_counter: int,
        timestamp: pd.Timestamp,
    ) -> tuple[float, int]:
        for _, row in rows.iterrows():
            symbol = str(row[self.config.symbol_col])
            signal = int(row[self.config.signal_col])
            if symbol in positions and previous_signals.get(symbol, 0) == 1 and signal == 0:
                cash, trade_counter = self._close_position(
                    position=positions.pop(symbol),
                    price=float(row[self.config.price_col]),
                    cash=cash,
                    trades=trades,
                    trade_counter=trade_counter,
                    timestamp=timestamp,
                    exit_reason="signal_flat",
                )
        return cash, trade_counter

    def _process_entries(
        self,
        rows: pd.DataFrame,
        positions: dict[str, Position],
        previous_signals: dict[str, int],
        cash: float,
        latest_prices: dict[str, float],
    ) -> float:
        for _, row in rows.iterrows():
            symbol = str(row[self.config.symbol_col])
            signal = int(row[self.config.signal_col])
            if signal != 1 or previous_signals.get(symbol, 0) == 1 or symbol in positions:
                continue

            equity = cash + self._market_value(positions, latest_prices)
            allocation_pct = min(self.config.position_size_pct, self.config.max_position_pct)
            allocation = equity * allocation_pct
            fill_price = self._buy_price(float(row[self.config.price_col]))
            quantity = allocation / fill_price
            total_cost = quantity * fill_price + self.config.commission_per_trade
            if total_cost > cash:
                continue
            cash -= total_cost
            positions[symbol] = Position(
                symbol=symbol,
                quantity=quantity,
                entry_price=fill_price,
                entry_timestamp=str(row[self.config.timestamp_col]),
            )
        return cash

    def _close_position(
        self,
        position: Position,
        price: float,
        cash: float,
        trades: list[Trade],
        trade_counter: int,
        timestamp: pd.Timestamp,
        exit_reason: str,
    ) -> tuple[float, int]:
        exit_price = self._sell_price(price)
        proceeds = position.quantity * exit_price
        cash += proceeds - self.config.commission_per_trade
        gross_pnl = (exit_price - position.entry_price) * position.quantity
        net_pnl = gross_pnl - (2 * self.config.commission_per_trade)
        return_pct = exit_price / position.entry_price - 1
        trades.append(
            Trade(
                trade_id=f"trade_{trade_counter}",
                symbol=position.symbol,
                entry_timestamp=position.entry_timestamp,
                exit_timestamp=str(timestamp),
                side="long",
                quantity=position.quantity,
                entry_price=position.entry_price,
                exit_price=exit_price,
                gross_pnl=gross_pnl,
                net_pnl=net_pnl,
                return_pct=return_pct,
                bars_held=position.bars_held,
                exit_reason=exit_reason,
            )
        )
        return cash, trade_counter + 1

    def _close_end_of_data(
        self,
        positions: dict[str, Position],
        latest_prices: dict[str, float],
        cash: float,
        trades: list[Trade],
        trade_counter: int,
        timestamp: pd.Timestamp,
    ) -> tuple[float, int]:
        for symbol, position in list(positions.items()):
            price = latest_prices.get(symbol)
            if price is None:
                continue
            cash, trade_counter = self._close_position(
                position=position,
                price=price,
                cash=cash,
                trades=trades,
                trade_counter=trade_counter,
                timestamp=timestamp,
                exit_reason="end_of_data",
            )
            positions.pop(symbol)
        return cash, trade_counter

    def _prices_for_rows(self, rows: pd.DataFrame) -> dict[str, float]:
        return {
            str(row[self.config.symbol_col]): float(row[self.config.price_col])
            for _, row in rows.iterrows()
        }

    def _market_value(self, positions: dict[str, Position], prices: dict[str, float]) -> float:
        value = 0.0
        for symbol, position in positions.items():
            price = prices.get(symbol, position.entry_price)
            value += position.quantity * price
        return value

    def _update_previous_signals(
        self,
        rows: pd.DataFrame,
        previous_signals: dict[str, int],
    ) -> None:
        for _, row in rows.iterrows():
            previous_signals[str(row[self.config.symbol_col])] = int(row[self.config.signal_col])

    def _buy_price(self, price: float) -> float:
        return price * (1 + self.config.slippage_bps / 10000)

    def _sell_price(self, price: float) -> float:
        return price * (1 - self.config.slippage_bps / 10000)


class BacktestEngine:
    """Compatibility wrapper for backtesting package imports."""

    def describe(self) -> str:
        """Return a short description of the component."""
        return "Runs research-only long/flat signal backtests with costs and slippage."
