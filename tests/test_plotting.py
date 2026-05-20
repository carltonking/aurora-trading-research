"""Tests for plotting module."""

import pytest
from unittest.mock import MagicMock, patch

import pandas as pd


def test_plot_equity_curve_no_matplotlib() -> None:
    """Test equity curve plotting when matplotlib is not available."""
    from aurora.reporting import plotting

    original_available = plotting.MATPLOTLIB_AVAILABLE
    plotting.MATPLOTLIB_AVAILABLE = False

    try:
        equity = pd.Series([100, 110, 105, 115], index=pd.date_range("2024-01-01", periods=4))
        plotting.plot_equity_curve(equity)
    finally:
        plotting.MATPLOTLIB_AVAILABLE = original_available


def test_plot_drawdown_no_matplotlib() -> None:
    """Test drawdown plotting when matplotlib is not available."""
    from aurora.reporting import plotting

    original_available = plotting.MATPLOTLIB_AVAILABLE
    plotting.MATPLOTLIB_AVAILABLE = False

    try:
        equity = pd.Series([100, 110, 105, 115], index=pd.date_range("2024-01-01", periods=4))
        plotting.plot_drawdown(equity)
    finally:
        plotting.MATPLOTLIB_AVAILABLE = original_available


def test_plot_rolling_sharpe_no_matplotlib() -> None:
    """Test rolling Sharpe plotting when matplotlib is not available."""
    from aurora.reporting import plotting

    original_available = plotting.MATPLOTLIB_AVAILABLE
    plotting.MATPLOTLIB_AVAILABLE = False

    try:
        returns = pd.Series([0.01, -0.02, 0.03, 0.01], index=pd.date_range("2024-01-01", periods=4))
        plotting.plot_rolling_sharpe(returns)
    finally:
        plotting.MATPLOTLIB_AVAILABLE = original_available


def test_plot_combined_report_no_matplotlib() -> None:
    """Test combined report when matplotlib is not available."""
    from aurora.reporting import plotting

    original_available = plotting.MATPLOTLIB_AVAILABLE
    plotting.MATPLOTLIB_AVAILABLE = False

    try:
        equity = pd.Series([100, 110, 105, 115], index=pd.date_range("2024-01-01", periods=4))
        result = plotting.plot_combined_report(equity)
        assert result is None
    finally:
        plotting.MATPLOTLIB_AVAILABLE = original_available


def test_matplotlib_available_flag() -> None:
    """Test that MATPLOTLIB_AVAILABLE flag is correctly set."""
    from aurora.reporting import plotting

    assert isinstance(plotting.MATPLOTLIB_AVAILABLE, bool)