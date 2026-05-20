"""Backtest Runner Screen."""

from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.screen import Screen
from textual.widgets import Static, Button, Input, DataTable, Label, Select


class BacktestRunnerScreen(Screen):
    """Backtest configuration and execution."""

    def compose(self) -> ComposeResult:
        yield Container(
            Static("[bold]Backtest Runner[/bold]", id="title"),
            Container(
                Label("Strategy:"),
                Select([("momentum", "Momentum"), ("mean_reversion", "Mean Reversion")], id="strategy"),
                Label("Symbol:"),
                Input(placeholder="SPY", id="symbol"),
                Label("Start Date:"),
                Input(placeholder="2020-01-01", id="start"),
                Label("End Date:"),
                Input(placeholder="2024-01-01", id="end"),
                Label("Walk-Forward:"),
                Select([("none", "None"), ("rolling", "Rolling"), ("expanding", "Expanding")], id="wf_method"),
                Button("Run Backtest", variant="primary", id="run_btn"),
                Button("Save Results", id="save_btn"),
                id="form",
            ),
            VerticalScroll(
                Static("Results:", id="results_title"),
                DataTable(id="results_table"),
                Static("Metrics:", id="metrics_title"),
                Static("Total Return: N/A\nSharpe: N/A\nMax Drawdown: N/A\nWin Rate: N/A", id="metrics"),
                id="results_panel",
            ),
        )

    def on_mount(self) -> None:
        self.query_one("#results_table").add_columns("Metric", "Value")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.notify("Backtest execution available via CLI: aurora backtest run")