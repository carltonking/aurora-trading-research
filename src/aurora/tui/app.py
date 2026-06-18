"""AURORA TUI - Main application."""

from __future__ import annotations

import os
from typing import Any, Optional

try:
    from textual.app import App
    from textual.binding import Binding
    from textual.containers import Container
    from textual.widgets import Static, Button, Input, DataTable, Footer, Header, TabbedContent, TabPane
except ImportError:
    raise ImportError(
        "Textual is not installed. Install with: pip install .[tui]"
    )

from aurora.tui.screens import (
    HomeScreen,
    DataExplorerScreen,
    StrategyBuilderScreen,
    BacktestRunnerScreen,
    PaperMonitorScreen,
    OptimizerScreen,
    ReadinessReportScreen,
    ExportScreen,
    SchedulerScreen,
    SettingsScreen,
    LogsScreen,
)

from aurora.tui.widgets import DisclaimerFooter
from aurora.tui.constants import APP_VERSION, MANDATORY_DISCLAIMER


class AuroraTUI(App):
    """Main Aurora TUI Application."""

    CSS_PATH = "styles.tcss"
    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", priority=True),
        Binding("f1", "switch_screen('home')", "Home"),
        Binding("f2", "switch_screen('data')", "Data"),
        Binding("f3", "switch_screen('strategy')", "Strategy"),
        Binding("f4", "switch_screen('backtest')", "Backtest"),
        Binding("f5", "switch_screen('paper')", "Paper"),
        Binding("f6", "switch_screen('optimizer')", "Optimize"),
        Binding("f7", "switch_screen('readiness')", "Readiness"),
        Binding("f8", "switch_screen('export')", "Export"),
        Binding("f9", "switch_screen('scheduler')", "Scheduler"),
        Binding("f10", "switch_screen('settings')", "Settings"),
        Binding("f11", "switch_screen('logs')", "Logs"),
        Binding("?", "toggle_help", "Help"),
    ]

    SCREENS = {
        "home": HomeScreen,
        "data": DataExplorerScreen,
        "strategy": StrategyBuilderScreen,
        "backtest": BacktestRunnerScreen,
        "paper": PaperMonitorScreen,
        "optimizer": OptimizerScreen,
        "readiness": ReadinessReportScreen,
        "export": ExportScreen,
        "scheduler": SchedulerScreen,
        "settings": SettingsScreen,
        "logs": LogsScreen,
    }

    def __init__(self, start_screen: str = "home", config_path: Optional[str] = None) -> None:
        super().__init__()
        self._start_screen = start_screen
        self._config_path = config_path

    def compose(self) -> Any:
        """Compose the app layout."""
        yield Header()
        with TabbedContent():
            for name, screen_cls in self.SCREENS.items():
                title = name.replace("_", " ").title()
                with TabPane(title):
                    yield screen_cls()
        yield DisclaimerFooter()
        yield Footer()

    def on_mount(self) -> None:
        """Set up initial screen and show welcome notification."""
        self.push_screen(self.SCREENS[self._start_screen]())
        self.notify(
            f"AURORA TUI v{APP_VERSION}\n{MANDATORY_DISCLAIMER}",
            title="Welcome to AURORA",
            timeout=10,
        )

    def action_switch_screen(self, screen_name: str) -> None:
        """Switch to a named screen."""
        if screen_name in self.SCREENS:
            self.push_screen(self.SCREENS[screen_name]())

    def action_toggle_help(self) -> None:
        """Show help overlay."""
        help_text = """
AURORA TUI Keyboard Shortcuts:
F1-Home  F2-Data  F3-Strategy  F4-Backtest
F5-Paper F6-Optimize F7-Readiness F8-Export
F9-Scheduler F10-Settings F11-Logs ?-Help Ctrl+Q-Quit
        """.strip()
        self.notify(help_text, title="Keyboard Help", timeout=5)


def check_textual() -> bool:
    """Check if Textual is available."""
    try:
        import textual
        return True
    except ImportError:
        return False


def launch_tui(start_screen: str = "home", config_path: Optional[str] = None) -> None:
    """Launch the TUI application."""
    if not check_textual():
        print("Textual is not installed. Install with: pip install .[tui]")
        return

    app = AuroraTUI(start_screen=start_screen, config_path=config_path)
    app.run()


if __name__ == "__main__":
    launch_tui()