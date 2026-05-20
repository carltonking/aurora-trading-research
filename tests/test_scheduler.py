"""Tests for task scheduler."""

import pytest
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from aurora.scheduling.scheduler import (
    ALLOWED_COMMANDS,
    ScheduledTask,
    TaskScheduler,
    validate_schedule,
)


def test_allowed_commands_defined() -> None:
    """Test that allowed commands are defined."""
    assert len(ALLOWED_COMMANDS) > 0
    assert "data fetch" in ALLOWED_COMMANDS
    assert "backtest run" in ALLOWED_COMMANDS
    assert "demo run" in ALLOWED_COMMANDS


def test_scheduled_task_creation() -> None:
    """Test creating a scheduled task."""
    task = ScheduledTask(
        name="test_task",
        command="data fetch --symbols SPY",
        interval_minutes=60,
    )

    assert task.name == "test_task"
    assert task.command == "data fetch --symbols SPY"
    assert task.interval_minutes == 60
    assert task.enabled is True
    assert task.next_run is not None


def test_scheduled_task_disabled() -> None:
    """Test disabled task is not due."""
    task = ScheduledTask(
        name="test_task",
        command="data fetch --symbols SPY",
        interval_minutes=60,
        enabled=False,
    )

    assert task.is_due() is False


def test_scheduled_task_is_due() -> None:
    """Test task is due when interval has passed."""
    task = ScheduledTask(
        name="test_task",
        command="data fetch --symbols SPY",
        interval_minutes=0,
    )

    assert task.is_due() is True


def test_scheduled_task_mark_run() -> None:
    """Test marking task as run updates times."""
    task = ScheduledTask(
        name="test_task",
        command="data fetch --symbols SPY",
        interval_minutes=60,
    )

    original_next = task.next_run
    task.mark_run()

    assert task.last_run is not None
    assert task.next_run is not None
    assert task.next_run > original_next


def test_task_scheduler_loads_valid_schedule() -> None:
    """Test loading a valid schedule."""
    yaml_content = """
tasks:
  - name: test_task
    command: data fetch --symbols SPY
    interval: 60
    enabled: true
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        f.write(yaml_content)
        tmppath = f.name

    try:
        scheduler = TaskScheduler(tmppath)
        assert len(scheduler.tasks) == 1
        assert scheduler.tasks[0].name == "test_task"
    finally:
        Path(tmppath).unlink()


def test_task_scheduler_rejects_disallowed_command() -> None:
    """Test that disallowed commands are rejected."""
    yaml_content = """
tasks:
  - name: bad_task
    command: rm -rf /
    interval: 60
    enabled: true
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        f.write(yaml_content)
        tmppath = f.name

    try:
        with pytest.raises(ValueError, match="disallowed command"):
            TaskScheduler(tmppath)
    finally:
        Path(tmppath).unlink()


def test_task_scheduler_rejects_empty_command() -> None:
    """Test that empty commands are rejected."""
    yaml_content = """
tasks:
  - name: empty_task
    command: ""
    interval: 60
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        f.write(yaml_content)
        tmppath = f.name

    try:
        with pytest.raises(ValueError, match="empty command"):
            TaskScheduler(tmppath)
    finally:
        Path(tmppath).unlink()


def test_task_scheduler_file_not_found() -> None:
    """Test that missing file raises error."""
    with pytest.raises(FileNotFoundError):
        TaskScheduler("/nonexistent/schedule.yml")


def test_task_scheduler_get_task() -> None:
    """Test getting a task by name."""
    yaml_content = """
tasks:
  - name: task_one
    command: data fetch --symbols SPY
    interval: 60
  - name: task_two
    command: backtest run
    interval: 120
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        f.write(yaml_content)
        tmppath = f.name

    try:
        scheduler = TaskScheduler(tmppath)
        task = scheduler.get_task("task_two")
        assert task is not None
        assert task.name == "task_two"
        assert task.command == "backtest run"

        missing = scheduler.get_task("nonexistent")
        assert missing is None
    finally:
        Path(tmppath).unlink()


def test_task_scheduler_list_tasks() -> None:
    """Test listing all tasks."""
    yaml_content = """
tasks:
  - name: active_task
    command: data fetch
    interval: 60
    enabled: true
  - name: disabled_task
    command: demo run
    interval: 120
    enabled: false
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        f.write(yaml_content)
        tmppath = f.name

    try:
        scheduler = TaskScheduler(tmppath)
        tasks = scheduler.list_tasks()

        assert len(tasks) == 2
        assert tasks[0]["name"] == "active_task"
        assert tasks[0]["enabled"] is True
        assert tasks[1]["name"] == "disabled_task"
        assert tasks[1]["enabled"] is False
    finally:
        Path(tmppath).unlink()


def test_validate_schedule_valid() -> None:
    """Test validating a valid schedule."""
    yaml_content = """
tasks:
  - name: valid_task
    command: data fetch
    interval: 60
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        f.write(yaml_content)
        tmppath = f.name

    try:
        is_valid, message = validate_schedule(tmppath)
        assert is_valid is True
        assert "1 task" in message
    finally:
        Path(tmppath).unlink()


def test_validate_schedule_invalid() -> None:
    """Test validating an invalid schedule."""
    yaml_content = """
tasks:
  - name: bad_task
    command: rm -rf /
    interval: 60
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        f.write(yaml_content)
        tmppath = f.name

    try:
        is_valid, message = validate_schedule(tmppath)
        assert is_valid is False
        assert "disallowed" in message
    finally:
        Path(tmppath).unlink()


def test_validate_schedule_missing_file() -> None:
    """Test validating a missing file."""
    is_valid, message = validate_schedule("/nonexistent.yml")
    assert is_valid is False
    assert "not found" in message


@patch("subprocess.run")
def test_run_once_executes_task(mock_run: MagicMock) -> None:
    """Test that run_once executes the task."""
    yaml_content = """
tasks:
  - name: test_task
    command: data fetch --symbols SPY
    interval: 60
    enabled: true
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        f.write(yaml_content)
        tmppath = f.name

    mock_run.return_value = MagicMock(returncode=0, stderr="")

    try:
        scheduler = TaskScheduler(tmppath)
        result = scheduler.run_once("test_task")

        assert result is True
        mock_run.assert_called_once()
    finally:
        Path(tmppath).unlink()


def test_run_once_missing_task() -> None:
    """Test that run_once returns False for missing task."""
    yaml_content = """
tasks:
  - name: test_task
    command: data fetch
    interval: 60
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        f.write(yaml_content)
        tmppath = f.name

    try:
        scheduler = TaskScheduler(tmppath)
        result = scheduler.run_once("nonexistent_task")

        assert result is False
    finally:
        Path(tmppath).unlink()


def test_run_once_disabled_task() -> None:
    """Test that run_once returns False for disabled task."""
    yaml_content = """
tasks:
  - name: disabled_task
    command: data fetch
    interval: 60
    enabled: false
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        f.write(yaml_content)
        tmppath = f.name

    try:
        scheduler = TaskScheduler(tmppath)
        result = scheduler.run_once("disabled_task")

        assert result is False
    finally:
        Path(tmppath).unlink()


def test_task_with_start_time() -> None:
    """Test task with specific start time."""
    task = ScheduledTask(
        name="morning_task",
        command="backtest run",
        interval_minutes=60,
        start_time="09:00",
    )

    assert task.start_time == "09:00"
    assert task.next_run is not None


def test_multiple_tasks_in_schedule() -> None:
    """Test loading schedule with multiple tasks."""
    yaml_content = """
tasks:
  - name: task_1
    command: data fetch --symbols SPY
    interval: 60
  - name: task_2
    command: backtest run --strategy momentum
    interval: 1440
  - name: task_3
    command: paper report --output data/reports
    interval: 10080
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        f.write(yaml_content)
        tmppath = f.name

    try:
        scheduler = TaskScheduler(tmppath)
        assert len(scheduler.tasks) == 3

        assert scheduler.tasks[0].name == "task_1"
        assert scheduler.tasks[0].interval_minutes == 60

        assert scheduler.tasks[1].name == "task_2"
        assert scheduler.tasks[1].interval_minutes == 1440

        assert scheduler.tasks[2].name == "task_3"
        assert scheduler.tasks[2].interval_minutes == 10080
    finally:
        Path(tmppath).unlink()


def test_allowed_command_prefixes() -> None:
    """Test that various allowed command forms are accepted."""
    allowed_commands = [
        "data fetch --symbols SPY",
        "backtest run --strategy momentum",
        "backtest portfolio --universe sp500",
        "demo run --output-root data/demo",
        "paper stream --duration 3600",
        "paper simulate --plan data/plan.json",
        "report readiness --output data/reports",
        "report safety-audit",
        "optimize analyze --strategy momentum",
        "research run --config .aurora.yml",
        "config validate --path .aurora.yml",
    ]

    for cmd in allowed_commands:
        yaml_content = f"""
tasks:
  - name: test
    command: {cmd}
    interval: 60
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            f.write(yaml_content)
            tmppath = f.name

        try:
            scheduler = TaskScheduler(tmppath)
            assert len(scheduler.tasks) == 1
        finally:
            Path(tmppath).unlink()