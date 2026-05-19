"""Chart-data helpers for dashboard and reports."""

import pandas as pd

from aurora.reporting.exceptions import AuroraReportingError


def equity_curve_chart_data(equity_curve: pd.DataFrame) -> pd.DataFrame:
    """Return sorted timestamp/equity chart data."""
    _require_columns(equity_curve, ["timestamp", "equity"])
    data = equity_curve[["timestamp", "equity"]].copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"])
    data["equity"] = pd.to_numeric(data["equity"], errors="coerce")
    return data.sort_values("timestamp").reset_index(drop=True)


def drawdown_chart_data(equity_curve: pd.DataFrame) -> pd.DataFrame:
    """Return timestamp/drawdown chart data from an equity curve."""
    data = equity_curve_chart_data(equity_curve)
    running_max = data["equity"].cummax()
    data["drawdown"] = data["equity"] / running_max - 1
    return data[["timestamp", "drawdown"]]


def trade_pnl_chart_data(trades: pd.DataFrame) -> pd.DataFrame:
    """Return trade PnL chart data if net_pnl is available."""
    columns = ["trade_id", "symbol", "net_pnl"]
    if trades.empty or "net_pnl" not in trades.columns:
        return pd.DataFrame(columns=columns)

    data = trades.copy()
    if "trade_id" not in data.columns:
        data["trade_id"] = range(1, len(data) + 1)
    if "symbol" not in data.columns:
        data["symbol"] = ""
    data["net_pnl"] = pd.to_numeric(data["net_pnl"], errors="coerce")
    return data[columns].reset_index(drop=True)


def _require_columns(df: pd.DataFrame, columns: list[str]) -> None:
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise AuroraReportingError(f"Missing required chart columns: {', '.join(missing)}")
