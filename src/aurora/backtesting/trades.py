"""Trade record helpers for research backtests."""

from dataclasses import asdict, dataclass

import pandas as pd


@dataclass(frozen=True)
class Trade:
    """Closed simulated long-only trade."""

    trade_id: str
    symbol: str
    entry_timestamp: str
    exit_timestamp: str | None
    side: str
    quantity: float
    entry_price: float
    exit_price: float | None
    gross_pnl: float | None
    net_pnl: float | None
    return_pct: float | None
    bars_held: int
    exit_reason: str | None


@dataclass
class Position:
    """Open simulated long-only position."""

    symbol: str
    quantity: float
    entry_price: float
    entry_timestamp: str
    bars_held: int = 0


def trade_to_dict(trade: Trade) -> dict:
    """Convert a Trade dataclass to a dictionary."""
    return asdict(trade)


def trades_to_dataframe(trades: list[Trade]) -> pd.DataFrame:
    """Convert trades to a dataframe."""
    columns = list(Trade.__dataclass_fields__)
    if not trades:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame([trade_to_dict(trade) for trade in trades], columns=columns)
