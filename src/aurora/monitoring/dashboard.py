"""Paper trading dashboard for real-time monitoring."""

import os
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Optional

try:
    from rich.console import Console
    from rich.layout import Layout
    from rich.live import Live
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

from aurora.brokers.alpaca_adapter import AlpacaPaperBrokerProtocol
from aurora.data.streaming import MarketDataStream


@dataclass
class Position:
    """Represents an open position."""
    symbol: str
    quantity: int
    avg_price: float
    market_price: float = 0.0
    unrealized_pnl: float = 0.0


@dataclass
class Order:
    """Represents a pending order."""
    id: str
    symbol: str
    side: str
    quantity: int
    order_type: str
    status: str


@dataclass
class Fill:
    """Represents an executed fill."""
    id: str
    symbol: str
    side: str
    quantity: int
    price: float
    timestamp: str


class PaperDashboard:
    """Real-time paper trading dashboard."""

    def __init__(
        self,
        broker: AlpacaPaperBrokerProtocol,
        stream: Optional[MarketDataStream] = None,
        update_interval: float = 1.0,
    ) -> None:
        self.broker = broker
        self.stream = stream
        self.update_interval = update_interval
        self.console = Console() if RICH_AVAILABLE else None
        self._running = False
        self._equity_history: list[float] = []
        self._start_time: Optional[datetime] = None

    def start(self, duration_seconds: int = 60) -> None:
        """Start the dashboard for specified duration."""
        self._running = True
        self._start_time = datetime.now(UTC)
        start = time.time()

        if RICH_AVAILABLE:
            self._run_rich(duration_seconds, start)
        else:
            self._run_plain(duration_seconds, start)

    def stop(self) -> None:
        """Stop the dashboard."""
        self._running = False

    def _run_rich(self, duration_seconds: int, start: float) -> None:
        """Run dashboard with rich formatting."""
        self.console.clear()
        while self._running and (time.time() - start) < duration_seconds:
            self.console.clear()
            self.console.print(self._make_layout())
            time.sleep(self.update_interval)

    def _make_layout(self) -> str:
        """Create the dashboard layout as string."""
        account = self._get_account_summary()
        positions = self._get_positions()
        orders = self._get_pending_orders()
        fills = self._get_recent_fills()
        equity_history = self._equity_history[-20:]
        risk = self._calculate_risk(positions)

        output = []
        output.append("=== Account Summary ===")
        for k, v in account.items():
            output.append(f"  {k}: {v}")

        output.append("\n=== Open Positions ===")
        for p in positions:
            output.append(f"  {p.symbol}: {p.quantity} @ {p.avg_price} (P&L: {p.unrealized_pnl:.2f})")

        output.append("\n=== Pending Orders ===")
        for o in orders:
            output.append(f"  {o.id[:8]}: {o.side} {o.quantity} {o.symbol}")

        output.append("\n=== Risk Gauges ===")
        output.append(f"  Exposure: {risk['exposure_pct']:.1f}%")
        output.append(f"  Day P&L: ${risk['total_pnl']:.2f}")
        output.append(f"  Positions: {risk['open_positions']}")

        return "\n".join(output)

    def _run_plain(self, duration_seconds: int, start: float) -> None:
        """Run dashboard with plain print fallback."""
        while self._running and (time.time() - start) < duration_seconds:
            self._print_plain()
            time.sleep(self.update_interval)

    def _print_plain(self) -> None:
        """Print plain text dashboard."""
        print("\n" + "=" * 60)
        print("PAPER TRADING DASHBOARD")
        print("=" * 60)

        account = self._get_account_summary()
        print("\n--- Account ---")
        for k, v in account.items():
            print(f"  {k}: {v}")

        positions = self._get_positions()
        print("\n--- Positions ---")
        for p in positions:
            print(f"  {p.symbol}: {p.quantity} @ {p.avg_price} (P&L: {p.unrealized_pnl:.2f})")

        orders = self._get_pending_orders()
        print("\n--- Pending Orders ---")
        for o in orders:
            print(f"  {o.id}: {o.side} {o.quantity} {o.symbol} ({o.status})")

        print("\n" + "=" * 60)

    def _get_account_summary(self) -> dict[str, Any]:
        """Get account summary from broker."""
        try:
            account = self.broker.get_account()
            return {
                "Cash": account.get("cash", "N/A"),
                "Equity": account.get("portfolio_value", "N/A"),
                "Buying Power": account.get("buying_power", "N/A"),
            }
        except Exception:
            return {"Cash": "N/A", "Equity": "N/A", "Buying Power": "N/A"}

    def _get_positions(self) -> list[Position]:
        """Get open positions from broker."""
        try:
            pos_list = self.broker.get_paper_positions()
            positions = []
            for p in pos_list:
                symbol = p.get("symbol", "")
                qty = int(p.get("qty", 0))
                avg_price = float(p.get("avg_cost", 0))
                market_price = float(p.get("current_price", avg_price))
                pnl = (market_price - avg_price) * qty
                positions.append(Position(
                    symbol=symbol,
                    quantity=qty,
                    avg_price=avg_price,
                    market_price=market_price,
                    unrealized_pnl=pnl,
                ))
            return positions
        except Exception:
            return []

    def _get_pending_orders(self) -> list[Order]:
        """Get pending orders from broker."""
        try:
            order_list = self.broker.get_paper_orders()
            orders = []
            for o in order_list:
                if o.get("status") in ("pending", "new", "open"):
                    orders.append(Order(
                        id=o.get("id", ""),
                        symbol=o.get("symbol", ""),
                        side=o.get("side", ""),
                        quantity=int(o.get("qty", 0)),
                        order_type=o.get("type", "market"),
                        status=o.get("status", "unknown"),
                    ))
            return orders[:10]
        except Exception:
            return []

    def _get_recent_fills(self) -> list[Fill]:
        """Get recent fills (from execution log if available)."""
        return []

    def _calculate_risk(self, positions: list[Position]) -> dict[str, Any]:
        """Calculate risk metrics."""
        total_exposure = sum(p.market_price * p.quantity for p in positions)
        equity = 100000.0
        exposure_pct = (total_exposure / equity * 100) if equity > 0 else 0
        total_pnl = sum(
            (p.market_price - p.avg_price) * p.quantity if p.unrealized_pnl == 0 else p.unrealized_pnl
            for p in positions
        )

        return {
            "exposure_pct": exposure_pct,
            "total_pnl": total_pnl,
            "open_positions": len(positions),
        }

    def _render_account(self, account: dict[str, Any]) -> Table:
        """Render account summary table."""
        table = Table(show_header=False, box=None)
        table.add_column("Key")
        table.add_column("Value")
        for k, v in account.items():
            table.add_row(k, str(v))
        return table

    def _render_positions(self, positions: list[Position]) -> Table:
        """Render positions table."""
        table = Table()
        table.add_column("Symbol")
        table.add_column("Qty")
        table.add_column("Avg")
        table.add_column("Market")
        table.add_column("P&L", justify="right")
        for p in positions:
            pnl_color = "green" if p.unrealized_pnl >= 0 else "red"
            table.add_row(
                p.symbol,
                str(p.quantity),
                f"{p.avg_price:.2f}",
                f"{p.market_price:.2f}",
                f"[{pnl_color}]{p.unrealized_pnl:.2f}[/{pnl_color}]",
            )
        return table

    def _render_orders(self, orders: list[Order]) -> Table:
        """Render orders table."""
        table = Table()
        table.add_column("ID")
        table.add_column("Symbol")
        table.add_column("Side")
        table.add_column("Qty")
        table.add_column("Status")
        for o in orders:
            table.add_row(
                o.id[:8],
                o.symbol,
                o.side,
                str(o.quantity),
                o.status,
            )
        return table

    def _render_fills(self, fills: list[Fill]) -> Table:
        """Render fills table."""
        if not fills:
            return Table.from_markup("[dim]No recent fills[/]")
        table = Table()
        table.add_column("Time")
        table.add_column("Symbol")
        table.add_column("Side")
        table.add_column("Qty")
        table.add_column("Price")
        for f in fills:
            table.add_row(
                f.timestamp[-8:],
                f.symbol,
                f.side,
                str(f.quantity),
                f"{f.price:.2f}",
            )
        return table

    def _render_equity(self, history: list[float]) -> Table:
        """Render equity curve as simple bars."""
        table = Table(show_header=False, box=None)
        if not history:
            table.add_row("[dim]No equity data[/]")
            return table
        max_val = max(history) or 1
        for val in history:
            bar_len = int((val / max_val) * 20)
            table.add_row("█" * bar_len)
        return table

    def _render_risk(self, risk: dict[str, Any]) -> Table:
        """Render risk gauges."""
        table = Table(show_header=False, box=None)
        table.add_column("Metric")
        table.add_column("Value")
        table.add_row("Exposure %", f"{risk['exposure_pct']:.1f}%")
        table.add_row("Day P&L", f"${risk['total_pnl']:.2f}")
        table.add_row("Open Positions", str(risk['open_positions']))
        return table