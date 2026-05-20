"""Settings Screen."""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widgets import Static, Button, TextArea, Label


class SettingsScreen(Screen):
    """Project configuration and settings."""

    def compose(self) -> ComposeResult:
        yield Container(
            Static("[bold]Settings & Configuration[/bold]", id="title"),
            Horizontal(
                Container(
                    Static("Environment Configuration:", id="env_title"),
                    Static(
                        "Data Source: yfinance\n"
                        "Broker: fake (paper only)\n"
                        "Sandbox: DISABLED\n"
                        "Plugin Dir: ~/aurora/plugins\n"
                        "Max Drawdown: 0.3\n"
                        "Kill-Switch: Not configured",
                        id="env_config",
                    ),
                    Button("Reload Config", id="reload_btn"),
                    id="left_panel",
                ),
                Container(
                    Static("Project Config (.aurora.yml):", id="config_title"),
                    TextArea(id="config_editor", language="yaml"),
                    Button("Save Config", variant="primary", id="save_btn"),
                    id="right_panel",
                ),
                id="main_layout",
            ),
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save_btn":
            self.notify("Config saved to .aurora.yml")
        elif event.button.id == "reload_btn":
            self.notify("Reloading configuration...")