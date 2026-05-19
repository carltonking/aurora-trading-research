"""Summary helpers for local research artifacts."""

from collections import Counter
from dataclasses import asdict, is_dataclass
from typing import Any

import pandas as pd


def summarize_dataframe(df: pd.DataFrame) -> dict[str, Any]:
    """Summarize a dataframe for local inspection."""
    summary: dict[str, Any] = {
        "row_count": len(df),
        "column_count": len(df.columns),
        "columns": list(df.columns),
        "numeric_columns": list(df.select_dtypes(include="number").columns),
    }
    if "timestamp" in df.columns:
        timestamps = pd.to_datetime(df["timestamp"], errors="coerce").dropna()
        summary["start_timestamp"] = timestamps.min().isoformat() if not timestamps.empty else None
        summary["end_timestamp"] = timestamps.max().isoformat() if not timestamps.empty else None
    if "symbol" in df.columns:
        summary["symbols"] = sorted(str(symbol) for symbol in df["symbol"].dropna().unique())
    return summary


def summarize_backtest_metrics(metrics: dict) -> dict[str, Any]:
    """Return a cleaned subset of backtest metrics."""
    keys = [
        "total_return",
        "annualized_return",
        "sharpe_ratio",
        "max_drawdown",
        "win_rate",
        "profit_factor",
        "trade_count",
        "exposure_pct",
        "final_equity",
        "starting_equity",
    ]
    return {key: metrics[key] for key in keys if key in metrics}


def summarize_orders(orders: list[dict]) -> dict[str, Any]:
    """Summarize local simulated orders."""
    statuses = Counter(str(order.get("status")) for order in orders if order.get("status") is not None)
    risk_statuses = Counter(
        str(order.get("risk_status")) for order in orders if order.get("risk_status") is not None
    )
    return {
        "order_count": len(orders),
        "filled_count": statuses.get("FILLED", 0),
        "rejected_count": statuses.get("REJECTED", 0),
        "symbols": sorted({str(order["symbol"]) for order in orders if order.get("symbol")}),
        "latest_timestamp": _latest_timestamp(orders),
        "risk_status_counts": dict(risk_statuses),
    }


def summarize_risk_decisions(decisions: list[dict]) -> dict[str, Any]:
    """Summarize local risk decisions."""
    statuses = Counter(
        str(decision.get("status")) for decision in decisions if decision.get("status") is not None
    )
    return {
        "decision_count": len(decisions),
        "approved_count": sum(1 for decision in decisions if decision.get("approved") is True),
        "rejected_count": sum(1 for decision in decisions if decision.get("approved") is False),
        "status_counts": dict(statuses),
        "latest_timestamp": _latest_timestamp(decisions),
    }


def summarize_positions(positions: dict | list[dict]) -> dict[str, Any]:
    """Summarize current local positions."""
    position_rows = _normalize_positions(positions)
    total_market_value = 0.0
    has_market_value = False
    for position in position_rows:
        quantity = float(position.get("quantity", 0.0) or 0.0)
        market_price = position.get("market_price")
        if market_price is not None:
            total_market_value += quantity * float(market_price)
            has_market_value = True

    return {
        "position_count": len(position_rows),
        "symbols": sorted(str(position.get("symbol")) for position in position_rows if position.get("symbol")),
        "total_quantity": sum(float(position.get("quantity", 0.0) or 0.0) for position in position_rows),
        "total_market_value": total_market_value if has_market_value else None,
    }


def _normalize_positions(positions: dict | list[dict]) -> list[dict]:
    if isinstance(positions, list):
        return [_to_plain_dict(position) for position in positions]
    rows = []
    for symbol, position in positions.items():
        row = _to_plain_dict(position)
        row.setdefault("symbol", symbol)
        rows.append(row)
    return rows


def _to_plain_dict(value: Any) -> dict:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return dict(value)
    return dict(value)


def _latest_timestamp(items: list[dict]) -> str | None:
    timestamps = []
    for item in items:
        timestamp = item.get("timestamp")
        if timestamp is None and isinstance(item.get("candidate"), dict):
            timestamp = item["candidate"].get("timestamp")
        if timestamp is not None:
            timestamps.append(timestamp)
    parsed = pd.to_datetime(pd.Series(timestamps), errors="coerce").dropna()
    return parsed.max().isoformat() if not parsed.empty else None
