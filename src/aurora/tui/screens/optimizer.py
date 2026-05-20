"""Optimizer Screen."""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widgets import Static, Button, TextArea, Select, DataTable, Label, ProgressBar, Input


class OptimizerScreen(Screen):
    """Strategy optimization configuration."""

    def compose(self) -> ComposeResult:
        yield Container(
            Static("[bold]Strategy Optimizer[/bold]", id="title"),
            Horizontal(
                Container(
                    Label("Parameter Space (JSON):"),
                    TextArea(id="param_space", language="json"),
                    Label("Method:"),
                    Select([("bayesian", "Bayesian"), ("genetic", "Genetic")], id="method"),
                    Label("Metric:"),
                    Select([("sharpe", "Sharpe Ratio"), ("returns", "Total Return"), ("win_rate", "Win Rate")], id="metric"),
                    Label("Max Iterations:"),
                    Input(placeholder="50", id="iterations"),
                    Button("Run Optimization", variant="primary", id="run_btn"),
                    Button("Save Proposal", id="save_btn"),
                    id="left_panel",
                ),
                Container(
                    Static("Progress:", id="progress_title"),
                    ProgressBar(total=100, id="progress_bar"),
                    Static("Log:", id="log_title"),
                    TextArea(id="log", read_only=True),
                    Static("Best Parameters:", id="best_title"),
                    DataTable(id="best_params"),
                    id="right_panel",
                ),
                id="main_layout",
            ),
        )

    def on_mount(self) -> None:
        self.query_one("#best_params").add_columns("Parameter", "Value", "Fitness")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "run_btn":
            self.notify("Run optimizer via CLI: aurora optimize analyze")
        elif event.button.id == "save_btn":
            self.notify("Save proposal via CLI after optimization")