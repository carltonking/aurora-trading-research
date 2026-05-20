"""Readiness Report Screen."""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widgets import Static, Button, TextArea, Label, Input


class ReadinessReportScreen(Screen):
    """Readiness report generation."""

    def compose(self) -> ComposeResult:
        yield Container(
            Static("[bold]Readiness Report[/bold]", id="title"),
            Container(
                Label("Strategy Name:"),
                Input(placeholder="momentum_strategy", id="strategy"),
                Label("Artifact Directory:"),
                Input(placeholder="data/demo/research_runs", id="artifact_dir"),
                Label("Paper Metrics Path (optional):"),
                Input(placeholder="data/demo/paper_metrics.json", id="paper_metrics"),
                Label("Optimization Proposal (optional):"),
                Input(placeholder="data/optimization/proposal.json", id="proposal"),
                Button("Generate Report", variant="primary", id="generate_btn"),
                Button("Export PDF", id="pdf_btn"),
                Button("Save JSON", id="json_btn"),
                id="form",
            ),
            Container(
                Static("Report Preview:", id="preview_title"),
                TextArea(id="report_preview", read_only=True),
                id="preview_panel",
            ),
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "generate_btn":
            self.notify("Generate report via CLI: aurora report readiness")
        elif event.button.id == "pdf_btn":
            self.notify("Export PDF requires Phase 6R PDF module")
        elif event.button.id == "json_btn":
            self.notify("Save JSON via CLI after generation")