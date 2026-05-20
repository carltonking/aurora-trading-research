"""Tests for TUI module."""

import pytest


def test_tui_module_import() -> None:
    """Test that TUI module can be imported when Textual is available."""
    try:
        from aurora.tui import AuroraTUI
        assert AuroraTUI is not None
    except ImportError:
        pytest.skip("Textual not installed")


def test_tui_app_class_exists() -> None:
    """Test that AuroraTUI class exists."""
    try:
        from aurora.tui.app import AuroraTUI
        assert hasattr(AuroraTUI, "CSS_PATH")
        assert hasattr(AuroraTUI, "BINDINGS")
        assert hasattr(AuroraTUI, "SCREENS")
    except ImportError:
        pytest.skip("Textual not installed")


def test_tui_screens_exist() -> None:
    """Test that all screen classes exist."""
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

    screens = [
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
    ]

    assert len(screens) == 11


def test_tui_widgets_exist() -> None:
    """Test that widget classes exist."""
    from aurora.tui.widgets import MetricCard, DisclaimerFooter, SparklineChart

    assert MetricCard is not None
    assert DisclaimerFooter is not None
    assert SparklineChart is not None


def test_tui_constants_defined() -> None:
    """Test that constants are defined."""
    from aurora.tui.constants import APP_VERSION, MANDATORY_DISCLAIMER

    assert APP_VERSION == "3.0.0"
    assert "DISCLAIMER" in MANDATORY_DISCLAIMER
    assert "research-only" in MANDATORY_DISCLAIMER


def test_check_textual_function() -> None:
    """Test check_textual function."""
    from aurora.tui.app import check_textual

    result = check_textual()
    assert isinstance(result, bool)


def test_launch_tui_import() -> None:
    """Test launch_tui function can be imported."""
    from aurora.tui.app import launch_tui

    assert callable(launch_tui)


def test_cli_command_exists() -> None:
    """Test that CLI command exists."""
    from aurora.cli.app import tui_start
    assert tui_start is not None


def test_sparkline_chart_render() -> None:
    """Test SparklineChart render method."""
    from aurora.tui.widgets import SparklineChart

    chart = SparklineChart()
    result = chart.render()
    assert result == "No data"

    chart.update([1, 2, 3, 4, 5])
    result = chart.render()
    assert "█" in result or "▄" in result


def test_metric_card_basic() -> None:
    """Test MetricCard basic rendering."""
    from aurora.tui.widgets import MetricCard

    card = MetricCard("Sharpe", "1.25")
    assert card is not None


def test_scheduler_screen_class() -> None:
    """Test SchedulerScreen exists and has compose method."""
    from aurora.tui.screens import SchedulerScreen

    assert SchedulerScreen is not None
    assert hasattr(SchedulerScreen, "compose")
    assert hasattr(SchedulerScreen, "DEFAULT_YAML")
    assert "tasks:" in SchedulerScreen.DEFAULT_YAML


def test_scheduler_screen_binds_to_f9() -> None:
    """Test that scheduler is bound to F9 in app."""
    from aurora.tui.app import AuroraTUI

    binding_found = False
    for binding in AuroraTUI.BINDINGS:
        if "scheduler" in str(binding):
            binding_found = True
            assert binding.key == "f9"
            break

    assert binding_found, "Scheduler binding not found in BINDINGS"


def test_scheduler_screen_in_app_screens() -> None:
    """Test that scheduler is registered in SCREENS."""
    from aurora.tui.app import AuroraTUI

    assert "scheduler" in AuroraTUI.SCREENS
    from aurora.tui.screens import SchedulerScreen
    assert AuroraTUI.SCREENS["scheduler"] == SchedulerScreen