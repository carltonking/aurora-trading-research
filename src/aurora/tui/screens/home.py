"""Home Screen."""

from textual.app import ComposeResult
from textual.containers import Container, Grid
from textual.screen import Screen
from textual.widgets import Static, Button, Label
from aurora.tui.constants import APP_VERSION, MANDATORY_DISCLAIMER


class HomeScreen(Screen):
    """Welcome panel showing AURORA version and navigation."""

    def compose(self) -> ComposeResult:
        yield Container(
            Static(f"[bold cyan]AURORA Trading Research[/bold cyan]", id="title"),
            Static(f"Version: {APP_VERSION}", id="version"),
            Static("Test Count: 768 passed", id="tests"),
            Static("Safety Audit: WARN (37 warnings, 8 critical)", id="safety"),
            Static("", id="spacer"),
            Static("[bold]Quick Navigation:", id="nav_title"),
            Static("F2 - Data Explorer", id="nav1"),
            Static("F3 - Strategy Builder", id="nav2"),
            Static("F4 - Backtest Runner", id="nav3"),
            Static("F5 - Paper Monitor", id="nav4"),
            Static("F6 - Optimizer", id="nav5"),
            Static("F7 - Readiness Report", id="nav6"),
            Static("F8 - Export", id="nav7"),
            Static("", id="spacer2"),
            Static(f"[yellow]{MANDATORY_DISCLAIMER}[/yellow]", id="disclaimer"),
        )

    def on_mount(self) -> None:
        self.query_one("#title").styles.text_align = "center"
        self.query_one("#disclaimer").styles.text_align = "center"