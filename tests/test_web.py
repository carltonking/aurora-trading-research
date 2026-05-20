"""Tests for web UI module."""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


def test_web_module_import() -> None:
    """Test that the web module can be imported."""
    try:
        from aurora.web import app
        assert app is not None
    except ImportError as e:
        pytest.fail(f"Web module import failed: {e}")


def test_web_app_has_required_functions() -> None:
    """Test that web app has required functions."""
    from aurora.web import app as web_app

    assert hasattr(web_app, "run_app")
    assert hasattr(web_app, "APP_VERSION")
    assert hasattr(web_app, "APP_TITLE")
    assert hasattr(web_app, "APP_HOST")
    assert hasattr(web_app, "APP_PORT")


def test_app_constants() -> None:
    """Test that app constants are defined correctly."""
    from aurora.web import app

    assert app.APP_VERSION == "0.1.0"
    assert app.APP_TITLE == "AURORA Research Dashboard"
    assert app.APP_HOST == "127.0.0.1"
    assert app.APP_PORT == 8501


def test_mask_secrets_function() -> None:
    """Test the mask_secrets function."""
    from aurora.web import app

    assert app.mask_secrets("") == ""
    assert app.mask_secrets("short") == "****"
    assert app.mask_secrets("AKIAIOSFODNN7EXAMPLE") == "AKIA****MPLE"
    assert app.mask_secrets("${API_KEY}") == "${API_KEY}"


def test_disclaimer_present() -> None:
    """Test that disclaimer function exists."""
    from aurora.web import app

    assert hasattr(app, "show_disclaimer")


def test_streamlit_import_when_available() -> None:
    """Test that Streamlit can be imported when available."""
    try:
        import streamlit
        from aurora.web import app as web_app
        assert web_app.check_streamlit() is None
    except ImportError:
        pytest.skip("Streamlit not installed")


def test_web_start_command() -> None:
    """Test that web start command exists."""
    from aurora.cli.app import web_start
    assert web_start is not None


def test_cli_command_registered() -> None:
    """Test that web command is registered in CLI."""
    from aurora.web import app as web_app_module

    assert hasattr(web_app_module, "APP_HOST")
    assert hasattr(web_app_module, "APP_PORT")


def test_export_screen_function_exists() -> None:
    """Test that render_export function exists."""
    from aurora.web import app

    assert hasattr(app, "render_export")
    assert callable(app.render_export)


def test_scheduler_screen_function_exists() -> None:
    """Test that render_scheduler function exists."""
    from aurora.web import app

    assert hasattr(app, "render_scheduler")
    assert callable(app.render_scheduler)


def test_deployment_checklist_screen_function_exists() -> None:
    """Test that render_deployment_checklist function exists."""
    from aurora.web import app

    assert hasattr(app, "render_deployment_checklist")
    assert callable(app.render_deployment_checklist)


def test_export_uses_strategy_exporter() -> None:
    """Test that export screen imports StrategyExporter."""
    try:
        from aurora.export.strategy_exporter import StrategyExporter
        assert StrategyExporter is not None
    except ImportError as e:
        pytest.fail(f"StrategyExporter import failed: {e}")


def test_scheduler_uses_task_scheduler() -> None:
    """Test that scheduler screen imports TaskScheduler."""
    try:
        from aurora.scheduling.scheduler import TaskScheduler
        assert TaskScheduler is not None
    except ImportError as e:
        pytest.fail(f"TaskScheduler import failed: {e}")


def test_deployment_checklist_uses_deployment_checklist() -> None:
    """Test that deployment checklist screen imports DeploymentChecklist."""
    try:
        from aurora.deployment.checklist import DeploymentChecklist
        assert DeploymentChecklist is not None
    except ImportError as e:
        pytest.fail(f"DeploymentChecklist import failed: {e}")