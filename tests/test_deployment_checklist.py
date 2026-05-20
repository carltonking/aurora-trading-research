"""Tests for deployment checklist."""

import json
import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from aurora.deployment.checklist import (
    ChecklistItem,
    ChecklistResult,
    DeploymentChecklist,
    MANDATORY_DISCLAIMER,
    DEFAULT_CHECKLIST,
    create_default_checklist_file,
)


def test_mandatory_disclaimer_defined() -> None:
    """Test that mandatory disclaimer is defined."""
    assert MANDATORY_DISCLAIMER
    assert "advisory tool" in MANDATORY_DISCLAIMER
    assert "responsibility" in MANDATORY_DISCLAIMER


def test_default_checklist_defined() -> None:
    """Test that default checklist is defined."""
    assert DEFAULT_CHECKLIST
    assert "risk_killswitch_configured" in DEFAULT_CHECKLIST


def test_checklist_item_creation() -> None:
    """Test creating a checklist item."""
    item = ChecklistItem(
        id="test_item",
        category="risk",
        description="Test check",
        type="boolean",
    )

    assert item.id == "test_item"
    assert item.category == "risk"
    assert item.type == "boolean"


def test_checklist_result_creation() -> None:
    """Test creating a checklist result."""
    result = ChecklistResult(
        item_id="test_item",
        passed=True,
        details="Test passed",
    )

    assert result.item_id == "test_item"
    assert result.passed is True
    assert result.details == "Test passed"


def test_deployment_checklist_default() -> None:
    """Test loading default checklist."""
    checklist = DeploymentChecklist()

    assert len(checklist.items) > 0
    assert any(item.id == "risk_killswitch_configured" for item in checklist.items)


def test_deployment_checklist_load_file() -> None:
    """Test loading checklist from file."""
    yaml_content = """
checklist:
  - id: test_check
    category: test
    description: "Test check"
    type: boolean
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        tmppath = f.name

    try:
        checklist = DeploymentChecklist(tmppath)
        assert len(checklist.items) == 1
        assert checklist.items[0].id == "test_check"
    finally:
        Path(tmppath).unlink()


def test_run_boolean_check() -> None:
    """Test running a boolean check."""
    yaml_content = """
checklist:
  - id: test_bool
    category: test
    description: "Test boolean"
    type: boolean
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        tmppath = f.name

    try:
        checklist = DeploymentChecklist(tmppath)
        results = checklist.run(answers={"test_bool": True})

        result = next(r for r in results if r.item_id == "test_bool")
        assert result.passed is True
    finally:
        Path(tmppath).unlink()


def test_run_boolean_check_fail() -> None:
    """Test running a boolean check that fails."""
    checklist = DeploymentChecklist()

    results = checklist.run(answers={"risk_killswitch_configured": False})

    result = next(r for r in results if r.item_id == "risk_killswitch_configured")
    assert result.passed is False


def test_run_threshold_check() -> None:
    """Test running a threshold check."""
    yaml_content = """
checklist:
  - id: test_threshold
    category: test
    description: "Test threshold"
    type: threshold
    params:
      metric: sharpe_ratio
      operator: gt
      value: 0
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        tmppath = f.name

    try:
        checklist = DeploymentChecklist(tmppath)
        results = checklist.run(
            strategy_metrics={"sharpe_ratio": 1.5},
        )

        result = next(r for r in results if r.item_id == "test_threshold")
        assert result.passed is True
    finally:
        Path(tmppath).unlink()


def test_run_threshold_check_fail() -> None:
    """Test running a threshold check that fails."""
    yaml_content = """
checklist:
  - id: test_threshold_fail
    category: test
    description: "Test threshold"
    type: threshold
    params:
      metric: sharpe_ratio
      operator: gt
      value: 0
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        tmppath = f.name

    try:
        checklist = DeploymentChecklist(tmppath)
        results = checklist.run(
            strategy_metrics={"sharpe_ratio": -0.5},
        )

        result = next(r for r in results if r.item_id == "test_threshold_fail")
        assert result.passed is False
    finally:
        Path(tmppath).unlink()


def test_run_confirmation_check() -> None:
    """Test running a confirmation check."""
    yaml_content = """
checklist:
  - id: test_confirm
    category: legal
    description: "Test confirmation"
    type: confirmation
    prompt: "Do you acknowledge?"
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        tmppath = f.name

    try:
        checklist = DeploymentChecklist(tmppath)
        results = checklist.run(answers={"test_confirm": True})

        result = next(r for r in results if r.item_id == "test_confirm")
        assert result.passed is True
    finally:
        Path(tmppath).unlink()


def test_run_file_exists_check() -> None:
    """Test running a file exists check."""
    yaml_content = """
checklist:
  - id: test_file
    category: export
    description: "Test file exists"
    type: file_exists
    params:
      path: "strategy.py"
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        tmppath = f.name

    try:
        checklist = DeploymentChecklist(tmppath)

        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as zf:
            zip_path = zf.name

        try:
            import zipfile

            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("strategy.py", "# Strategy code")

            results = checklist.run(export_bundle_path=zip_path)

            result = next(r for r in results if r.item_id == "test_file")
            assert result.passed is True
        finally:
            Path(zip_path).unlink()
    finally:
        Path(tmppath).unlink()


def test_run_file_exists_check_missing() -> None:
    """Test file exists check when file is missing."""
    yaml_content = """
checklist:
  - id: test_file_missing
    category: export
    description: "Test file missing"
    type: file_exists
    params:
      path: "missing.py"
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        tmppath = f.name

    try:
        checklist = DeploymentChecklist(tmppath)

        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as zf:
            zip_path = zf.name

        try:
            import zipfile

            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("other.py", "# Other code")

            results = checklist.run(export_bundle_path=zip_path)

            result = next(r for r in results if r.item_id == "test_file_missing")
            assert result.passed is False
        finally:
            Path(zip_path).unlink()
    finally:
        Path(tmppath).unlink()


def test_is_ready_all_pass() -> None:
    """Test is_ready returns True when all pass."""
    checklist = DeploymentChecklist()

    results = [
        ChecklistResult("check1", True, "passed"),
        ChecklistResult("check2", True, "passed"),
    ]

    assert checklist.is_ready(results) is True


def test_is_ready_some_fail() -> None:
    """Test is_ready returns False when some fail."""
    checklist = DeploymentChecklist()

    results = [
        ChecklistResult("check1", True, "passed"),
        ChecklistResult("check2", False, "failed"),
    ]

    assert checklist.is_ready(results) is False


def test_generate_report() -> None:
    """Test generating a report."""
    checklist = DeploymentChecklist()

    results = [
        ChecklistResult("check1", True, "passed"),
        ChecklistResult("check2", False, "failed"),
    ]

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        tmppath = f.name

    try:
        checklist.generate_report(results, tmppath)

        with open(tmppath) as f:
            report = json.load(f)

        assert "mandatory_disclaimer" in report
        assert report["total_items"] == 2
        assert report["passed"] == 1
        assert report["failed"] == 1
    finally:
        Path(tmppath).unlink()


def test_create_default_checklist_file() -> None:
    """Test creating a default checklist file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "checklist.yaml")
        create_default_checklist_file(path)

        assert os.path.exists(path)

        with open(path) as f:
            content = f.read()
            assert "checklist:" in content
            assert "risk_killswitch_configured" in content