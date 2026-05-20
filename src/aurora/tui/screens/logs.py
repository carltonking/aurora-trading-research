"""Logs Screen."""

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import Static, Button, TextArea


class LogsScreen(Screen):
    """Log viewer and session logs."""

    def compose(self) -> ComposeResult:
        yield Container(
            Static("[bold]Logs[/bold]", id="title"),
            Container(
                TextArea("Session started at 2026-05-20T15:00:00Z\n" * 20, id="log_viewer", read_only=True),
                Button("Clear Logs", id="clear_btn"),
                id="log_panel",
            ),
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "clear_btn":
            self.query_one("#log_viewer").clear()
            self.notify("Logs cleared")