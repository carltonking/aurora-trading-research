"""Export Screen."""

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import Static, Button, DataTable, Label, Input


class ExportScreen(Screen):
    """Strategy export and deployment checklist."""

    def compose(self) -> ComposeResult:
        yield Container(
            Static("[bold]Strategy Export[/bold]", id="title"),
            Container(
                Label("Strategy Name:"),
                Input(placeholder="momentum_strategy", id="strategy"),
                Label("Output Path:"),
                Input(placeholder="exports/strategy.zip", id="output"),
                Button("Run Checklist", id="checklist_btn"),
                Button("Export Bundle", variant="primary", id="export_btn"),
                id="form",
            ),
            Container(
                Static("Checklist Results:", id="checklist_title"),
                DataTable(id="checklist"),
                id="checklist_panel",
            ),
        )

    def on_mount(self) -> None:
        self.query_one("#checklist").add_columns("Check", "Status", "Details")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "checklist_btn":
            self.notify("Run checklist via CLI: aurora deploy checklist")
        elif event.button.id == "export_btn":
            self.notify("Export via CLI: aurora export strategy")