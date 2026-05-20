"""Data Explorer Screen."""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widgets import Static, Input, Button, DataTable, Label, Select


class DataExplorerScreen(Screen):
    """Data exploration with symbol/interval selection."""

    def compose(self) -> ComposeResult:
        yield Container(
            Static("[bold]Data Explorer[/bold]", id="title"),
            Horizontal(
                Container(
                    Label("Symbol:"),
                    Input(placeholder="SPY", id="symbol"),
                    Label("Interval:"),
                    Select(
                        [("1d", "1 Day"), ("1h", "1 Hour"), ("15m", "15 Min"), ("5m", "5 Min")],
                        id="interval",
                    ),
                    Label("Start Date (YYYY-MM-DD):"),
                    Input(placeholder="2020-01-01", id="start_date"),
                    Label("End Date (YYYY-MM-DD):"),
                    Input(placeholder="2024-01-01", id="end_date"),
                    Button("Fetch Data", variant="primary", id="fetch_btn"),
                    Button("Export CSV", id="export_btn"),
                    id="form",
                ),
                Container(
                    Static("Data Table", id="table_title"),
                    DataTable(id="data_table"),
                    id="data_panel",
                ),
                id="main_layout",
            ),
        )

    def on_mount(self) -> None:
        self.query_one("#data_table").add_columns("Date", "Open", "High", "Low", "Close", "Volume")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "fetch_btn":
            self.notify("Fetching data... (Not implemented in this version)")
        elif event.button.id == "export_btn":
            self.notify("Export functionality available in CLI")