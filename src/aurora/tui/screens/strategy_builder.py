"""Strategy Builder Screen."""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widgets import Static, Button, Select, TextArea, Label, Input


class StrategyBuilderScreen(Screen):
    """Strategy building with archetype selection."""

    def compose(self) -> ComposeResult:
        yield Container(
            Static("[bold]Strategy Builder[/bold]", id="title"),
            Horizontal(
                Container(
                    Label("Archetype:"),
                    Select(
                        [
                            ("trend_following", "Trend Following"),
                            ("mean_reversion", "Mean Reversion"),
                            ("breakout", "Breakout"),
                            ("grid_trading", "Grid Trading"),
                            ("pairs_trading", "Pairs Trading"),
                            ("dca", "DCA"),
                            ("ensemble", "Ensemble"),
                        ],
                        id="archetype",
                    ),
                    Label("Parameters (JSON):"),
                    TextArea(id="params"),
                    Button("Build Strategy", variant="primary", id="build_btn"),
                    Button("Save Config", id="save_btn"),
                    Button("Run Quick Backtest", id="backtest_btn"),
                    id="form",
                ),
                Container(
                    Static("Generated Strategy Code:", id="code_title"),
                    TextArea(id="code_view", read_only=True),
                    id="code_panel",
                ),
                id="main_layout",
            ),
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "build_btn":
            self.notify("Building strategy... (Use CLI for full functionality)")
        elif event.button.id == "save_btn":
            self.notify("Save config functionality available in CLI")
        elif event.button.id == "backtest_btn":
            self.notify("Run backtest from CLI: aurora backtest run")