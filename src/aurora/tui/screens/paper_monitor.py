"""Paper Monitor Screen."""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widgets import Static, Button, DataTable, ProgressBar, Label


class PaperMonitorScreen(Screen):
    """Live paper trading monitoring."""

    def compose(self) -> ComposeResult:
        yield Container(
            Static("[bold]Paper Trading Monitor[/bold]", id="title"),
            Horizontal(
                Container(
                    Static("Account Summary:", id="acc_title"),
                    Static("Cash: $100,000.00\nEquity: $100,000.00\nBuying Power: $100,000.00", id="account"),
                    Static("Risk Gauges:", id="risk_title"),
                    ProgressBar(total=100, id="exposure_bar"),
                    ProgressBar(total=100, id="drawdown_bar"),
                    Static("Kill-Switch: [green]SAFE[/green]", id="killswitch"),
                    Button("Start Fake Stream", variant="primary", id="start_btn"),
                    Button("Stop Stream", id="stop_btn"),
                    id="left_panel",
                ),
                Container(
                    Static("Open Positions:", id="pos_title"),
                    DataTable(id="positions"),
                    Static("Recent Fills:", id="fills_title"),
                    DataTable(id="fills"),
                    id="right_panel",
                ),
                id="main_layout",
            ),
        )

    def on_mount(self) -> None:
        self.query_one("#positions").add_columns("Symbol", "Qty", "Price", "P&L")
        self.query_one("#fills").add_columns("Time", "Symbol", "Side", "Qty", "Price")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "start_btn":
            self.notify("Start paper stream via CLI: aurora paper stream")
        elif event.button.id == "stop_btn":
            self.notify("Stop stream with Ctrl+C in CLI")