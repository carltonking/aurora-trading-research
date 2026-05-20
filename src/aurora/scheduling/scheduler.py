"""Task scheduler for periodic research tasks.

This module provides a YAML-based scheduler for running research tasks
at defined intervals. All tasks are research-only, no live trading.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)

ALLOWED_COMMANDS = {
    "data fetch",
    "data cache",
    "backtest run",
    "backtest portfolio",
    "paper stream",
    "paper simulate",
    "paper report",
    "report readiness",
    "report safety-audit",
    "demo run",
    "optimize analyze",
    "research run",
    "config validate",
}

ALLOWED_COMMAND_PREFIXES = tuple(ALLOWED_COMMANDS)


@dataclass
class ScheduledTask:
    """Represents a scheduled task."""

    name: str
    command: str
    interval_minutes: int
    enabled: bool = True
    start_time: Optional[str] = None
    last_run: Optional[datetime] = field(default=None, init=False)
    next_run: Optional[datetime] = field(default=None, init=False)

    def __post_init__(self) -> None:
        """Calculate initial next_run time."""
        self._calculate_next_run()

    def _calculate_next_run(self) -> None:
        """Calculate the next run time based on interval."""
        now = datetime.now(UTC)

        if self.start_time:
            hour, minute = map(int, self.start_time.split(":"))
            target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

            if target_time <= now:
                target_time += timedelta(minutes=self.interval_minutes)
            self.next_run = target_time
        else:
            if self.last_run:
                self.next_run = self.last_run + timedelta(minutes=self.interval_minutes)
            else:
                self.next_run = now

    def is_due(self) -> bool:
        """Check if the task is due to run."""
        if not self.enabled:
            return False
        if self.next_run is None:
            return False
        return datetime.now(UTC) >= self.next_run

    def mark_run(self) -> None:
        """Mark the task as having run."""
        self.last_run = datetime.now(UTC)
        self._calculate_next_run()


class TaskScheduler:
    """Scheduler for running research tasks at defined intervals."""

    def __init__(self, schedule_yaml: str) -> None:
        """Initialize the scheduler from a YAML schedule file.

        Args:
            schedule_yaml: Path to the schedule YAML file.

        Raises:
            FileNotFoundError: If schedule file doesn't exist.
            ValueError: If schedule contains invalid or dangerous commands.
        """
        self._schedule_path = Path(schedule_yaml)
        if not self._schedule_path.exists():
            raise FileNotFoundError(f"Schedule file not found: {schedule_yaml}")

        self._tasks: list[ScheduledTask] = []
        self._running = False
        self._stop_event = threading.Event()

        self._load_schedule()

    def _load_schedule(self) -> None:
        """Load and validate the schedule from YAML."""
        with self._schedule_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        tasks_data = data.get("tasks", [])

        for task_data in tasks_data:
            name = task_data.get("name", "unnamed")
            command = task_data.get("command", "")
            interval = task_data.get("interval", 60)
            enabled = task_data.get("enabled", True)
            start_time = task_data.get("start_time", None)

            self._validate_command(command, name)

            task = ScheduledTask(
                name=name,
                command=command,
                interval_minutes=interval,
                enabled=enabled,
                start_time=start_time,
            )
            self._tasks.append(task)

        logger.info(f"Loaded {len(self._tasks)} tasks from {self._schedule_path}")

    def _validate_command(self, command: str, task_name: str) -> None:
        """Validate that a command is allowed.

        Args:
            command: The command string to validate.
            task_name: Name of the task (for error message).

        Raises:
            ValueError: If command is not allowed.
        """
        command_stripped = command.strip()

        if not command_stripped:
            raise ValueError(f"Task '{task_name}' has empty command")

        is_allowed = command_stripped.startswith(ALLOWED_COMMAND_PREFIXES)
        is_subcommand = any(command_stripped.startswith(p + " ") for p in ALLOWED_COMMAND_PREFIXES)

        if not (is_allowed or is_subcommand):
            raise ValueError(
                f"Task '{task_name}' has disallowed command '{command_stripped}'. "
                f"Allowed commands must start with: {', '.join(ALLOWED_COMMANDS)}"
            )

    @property
    def tasks(self) -> list[ScheduledTask]:
        """Get list of scheduled tasks."""
        return self._tasks

    def get_task(self, name: str) -> Optional[ScheduledTask]:
        """Get a task by name."""
        for task in self._tasks:
            if task.name == name:
                return task
        return None

    def run_once(self, task_name: str) -> bool:
        """Manually trigger a task by name.

        Args:
            task_name: Name of the task to run.

        Returns:
            True if task was found and executed, False otherwise.
        """
        task = self.get_task(task_name)
        if task is None:
            logger.error(f"Task not found: {task_name}")
            return False

        if not task.enabled:
            logger.warning(f"Task '{task_name}' is disabled")
            return False

        logger.info(f"Running task '{task_name}': {task.command}")
        return self._execute_task(task)

    def _execute_task(self, task: ScheduledTask) -> bool:
        """Execute a task in a subprocess.

        Args:
            task: The task to execute.

        Returns:
            True if execution succeeded, False otherwise.
        """
        try:
            full_command = f"aurora {task.command}"

            result = subprocess.run(
                [sys.executable, "-m", "aurora.cli.app"] + task.command.split(),
                capture_output=True,
                text=True,
                timeout=3600,
            )

            if result.returncode == 0:
                logger.info(f"Task '{task.name}' completed successfully")
                task.mark_run()
                return True
            else:
                logger.error(f"Task '{task.name}' failed: {result.stderr}")
                task.mark_run()
                return False

        except subprocess.TimeoutExpired:
            logger.error(f"Task '{task.name}' timed out after 1 hour")
            return False
        except Exception as e:
            logger.error(f"Task '{task.name}' error: {e}")
            return False

    def run_forever(self, check_interval: int = 10) -> None:
        """Run the scheduler loop.

        This runs indefinitely until KeyboardInterrupt or SIGTERM.
        It checks for due tasks and executes them in separate threads.

        Args:
            check_interval: Seconds between checks (default 10).
        """
        self._running = True
        logger.info("Scheduler started")

        try:
            while not self._stop_event.is_set():
                for task in self._tasks:
                    if task.is_due():
                        thread = threading.Thread(target=self._execute_task, args=(task,))
                        thread.daemon = True
                        thread.start()

                self._stop_event.wait(check_interval)

        except KeyboardInterrupt:
            logger.info("Scheduler interrupted")
        finally:
            self._running = False
            logger.info("Scheduler stopped")

    def stop(self) -> None:
        """Signal the scheduler to stop."""
        self._stop_event.set()

    def list_tasks(self) -> list[dict[str, Any]]:
        """Get a list of tasks with their status.

        Returns:
            List of task info dictionaries.
        """
        result = []
        now = datetime.now(UTC)

        for task in self._tasks:
            result.append({
                "name": task.name,
                "command": task.command,
                "interval_minutes": task.interval_minutes,
                "enabled": task.enabled,
                "start_time": task.start_time,
                "last_run": task.last_run.isoformat() if task.last_run else None,
                "next_run": task.next_run.isoformat() if task.next_run else None,
                "is_due": task.is_due(),
            })

        return result


def validate_schedule(path: str) -> tuple[bool, str]:
    """Validate a schedule file without executing it.

    Args:
        path: Path to the schedule YAML file.

    Returns:
        Tuple of (is_valid, message).
    """
    try:
        scheduler = TaskScheduler(path)
        task_count = len(scheduler.tasks)
        return True, f"Valid schedule with {task_count} task(s)"
    except FileNotFoundError:
        return False, f"Schedule file not found: {path}"
    except ValueError as e:
        return False, str(e)
    except Exception as e:
        return False, f"Error loading schedule: {e}"