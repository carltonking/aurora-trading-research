"""Scheduler Screen."""

import threading
from typing import Optional

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widgets import Static, Button, DataTable, TextArea, Label


class SchedulerScreen(Screen):
    """Task scheduler configuration and control."""

    _scheduler: Optional[object] = None
    _scheduler_thread: Optional[threading.Thread] = None
    _running: bool = False
    _log_messages: list[str] = []

    DEFAULT_YAML = """tasks:
  - name: daily_research
    command: research run
    interval: 60
    enabled: true
    start_time: "09:00"

  - name: weekly_backtest
    command: backtest run --symbols SPY
    interval: 10080
    enabled: false
"""

    def compose(self) -> ComposeResult:
        yield Container(
            Static("[bold]Task Scheduler[/bold]", id="title"),
            Container(
                Label("Schedule YAML Configuration:", id="yaml_label"),
                TextArea.code(self.DEFAULT_YAML, language="yaml", id="schedule_yaml"),
                Horizontal(
                    Button("Validate", variant="primary", id="validate_btn"),
                    Button("Start Scheduler", variant="success", id="start_btn"),
                    Button("Stop Scheduler", variant="error", id="stop_btn"),
                    id="button_bar",
                ),
                id="config_panel",
            ),
            Container(
                Static("Task Status:", id="tasks_label"),
                DataTable(id="task_table"),
                id="tasks_panel",
            ),
            Container(
                Static("Log Messages:", id="log_label"),
                TextArea("", id="log_output", read_only=True),
                id="log_panel",
            ),
        )

    def on_mount(self) -> None:
        table = self.query_one("#task_table", DataTable)
        table.add_columns("Name", "Interval (min)", "Enabled", "Last Run", "Next Run")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "validate_btn":
            self._validate_schedule()
        elif event.button.id == "start_btn":
            self._start_scheduler()
        elif event.button.id == "stop_btn":
            self._stop_scheduler()

    def _validate_schedule(self) -> None:
        yaml_content = self.query_one("#schedule_yaml", TextArea).text
        try:
            import tempfile
            import yaml as pyyaml
            from aurora.scheduling.scheduler import validate_schedule

            with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
                f.write(yaml_content)
                temp_path = f.name

            is_valid, message = validate_schedule(temp_path)

            import os
            os.unlink(temp_path)

            if is_valid:
                self.notify(message, title="Validation", severity="information")
                self._load_tasks(yaml_content)
            else:
                self.notify(f"Validation failed: {message}", title="Validation Error", severity="error")

        except Exception as e:
            self.notify(f"Error: {e}", title="Validation Error", severity="error")

    def _load_tasks(self, yaml_content: str) -> None:
        try:
            import yaml
            from aurora.scheduling.scheduler import TaskScheduler
            import tempfile

            with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
                f.write(yaml_content)
                temp_path = f.name

            scheduler = TaskScheduler(temp_path)
            tasks = scheduler.list_tasks()

            import os
            os.unlink(temp_path)

            table = self.query_one("#task_table", DataTable)
            table.clear()

            for task in tasks:
                table.add_row(
                    task["name"],
                    str(task["interval_minutes"]),
                    "Yes" if task["enabled"] else "No",
                    task["last_run"][:19] if task["last_run"] else "Never",
                    task["next_run"][:19] if task["next_run"] else "N/A",
                )

        except Exception as e:
            self.notify(f"Error loading tasks: {e}", severity="error")

    def _start_scheduler(self) -> None:
        if self._running:
            self.notify("Scheduler is already running", severity="warning")
            return

        yaml_content = self.query_one("#schedule_yaml", TextArea).text

        try:
            import tempfile
            from aurora.scheduling.scheduler import TaskScheduler

            with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
                f.write(yaml_content)
                temp_path = f.name

            self._scheduler = TaskScheduler(temp_path)
            self._running = True

            self._log_messages.append(f"[INFO] Scheduler started at {self._scheduler.tasks}")

            def run_loop():
                try:
                    self._scheduler.run_forever(check_interval=30)
                except Exception as e:
                    self._log_messages.append(f"[ERROR] {e}")
                    self._running = False
                    self.notify(f"Scheduler error: {e}", severity="error")

            self._scheduler_thread = threading.Thread(target=run_loop, daemon=True)
            self._scheduler_thread.start()

            self._refresh_tasks()
            self.notify("Scheduler started", title="Scheduler", severity="information")

        except Exception as e:
            self.notify(f"Failed to start scheduler: {e}", severity="error")

    def _stop_scheduler(self) -> None:
        if not self._running:
            self.notify("Scheduler is not running", severity="warning")
            return

        try:
            if self._scheduler:
                self._scheduler.stop()
            self._running = False
            self._log_messages.append("[INFO] Scheduler stopped")
            self.notify("Scheduler stopped", title="Scheduler", severity="information")
            self._update_log_output()
        except Exception as e:
            self.notify(f"Failed to stop scheduler: {e}", severity="error")

    def _refresh_tasks(self) -> None:
        if self._scheduler:
            tasks = self._scheduler.list_tasks()
            table = self.query_one("#task_table", DataTable)
            table.clear()

            for task in tasks:
                table.add_row(
                    task["name"],
                    str(task["interval_minutes"]),
                    "Yes" if task["enabled"] else "No",
                    task["last_run"][:19] if task["last_run"] else "Never",
                    task["next_run"][:19] if task["next_run"] else "N/A",
                )

    def _update_log_output(self) -> None:
        log_area = self.query_one("#log_output", TextArea)
        log_area.text = "\n".join(self._log_messages[-50:])