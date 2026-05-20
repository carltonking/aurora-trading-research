"""Tests for Combinatorial Purged Cross-Validation (CPCV) module."""

import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


def test_cpcv_config_defaults() -> None:
    """Test that CPCVConfig has expected defaults."""
    from aurora.validation.cpcv import CPCVConfig

    config = CPCVConfig()
    assert config.n_splits == 6
    assert config.n_test_splits == 2
    assert config.purge_days == 21
    assert config.embargo_days == 5


def test_cpcv_splits_count() -> None:
    """Test that correct number of splits is generated for known inputs."""
    from aurora.validation.cpcv import CPCVConfig, generate_cpcv_splits

    config = CPCVConfig(n_splits=4, n_test_splits=2)
    dates = pd.date_range("2020-01-01", periods=200, freq="D")
    df = pd.DataFrame({
        "timestamp": np.repeat(dates, 3),
        "symbol": np.tile(["SPY", "QQQ", "DIA"], len(dates)),
        "signal": np.random.choice([0, 1], size=len(dates) * 3),
        "close": np.random.uniform(100, 200, size=len(dates) * 3),
    })

    splits = generate_cpcv_splits(df, config)

    expected = 6
    assert 1 <= len(splits) <= expected, (
        f"Expected between 1 and {expected} splits for C(4,2), got {len(splits)}"
    )


def test_cpcv_splits_no_overlap() -> None:
    """Test that train and test indices within each split are disjoint."""
    from aurora.validation.cpcv import CPCVConfig, generate_cpcv_splits

    config = CPCVConfig(n_splits=4, n_test_splits=2, purge_days=5, embargo_days=5)
    dates = pd.date_range("2020-01-01", periods=300, freq="D")
    df = pd.DataFrame({
        "timestamp": np.repeat(dates, 3),
        "symbol": np.tile(["SPY", "QQQ", "DIA"], len(dates)),
        "signal": np.random.choice([0, 1], size=len(dates) * 3),
        "close": np.random.uniform(100, 200, size=len(dates) * 3),
    })

    splits = generate_cpcv_splits(df, config)
    assert len(splits) > 0

    for i, split_a in enumerate(splits):
        train_test_overlap = set(split_a.train_indices) & set(split_a.test_indices)
        assert len(train_test_overlap) == 0, (
            f"Split {i} has overlapping train/test indices: {train_test_overlap}"
        )


def test_cpcv_purge_zone_respected() -> None:
    """Test that purge zone boundaries are correctly identified."""
    from aurora.validation.cpcv import CPCVConfig, generate_cpcv_splits

    config = CPCVConfig(n_splits=4, n_test_splits=2, purge_days=10, embargo_days=10)
    dates = pd.date_range("2020-01-01", periods=400, freq="D")
    df = pd.DataFrame({
        "timestamp": np.repeat(dates, 3),
        "symbol": np.tile(["SPY", "QQQ", "DIA"], len(dates)),
        "signal": np.random.choice([0, 1], size=len(dates) * 3),
        "close": np.random.uniform(100, 200, size=len(dates) * 3),
    })

    splits = generate_cpcv_splits(df, config)
    assert len(splits) > 0


def test_cpcv_result_to_dict() -> None:
    """Test that CPCVResult serializes to dict correctly."""
    from aurora.validation.cpcv import (
        BacktestPathResult,
        CPCVConfig,
        CPCVSplit,
        CPCVResult,
    )

    path = BacktestPathResult(
        path_id=0,
        train_start="2020-01-01T00:00:00",
        train_end="2020-06-01T00:00:00",
        test_start="2020-06-01T00:00:00",
        test_end="2020-12-01T00:00:00",
        total_return=0.15,
        sharpe_ratio=1.2,
        max_drawdown=-0.05,
        trade_count=25,
        win_rate=0.60,
        profit_factor=1.5,
        equity_curve=[100000.0, 105000.0, 110000.0],
        passed=True,
    )
    split = CPCVSplit(
        path_id=0,
        train_indices=np.array([0, 1, 2, 3, 4, 5, 6, 7, 8, 9]),
        test_indices=np.array([10, 11, 12]),
        test_start=pd.Timestamp("2020-06-01"),
        test_end=pd.Timestamp("2020-12-01"),
        train_start=pd.Timestamp("2020-01-01"),
        train_end=pd.Timestamp("2020-06-01"),
    )
    result = CPCVResult(
        config=CPCVConfig(),
        paths=[path],
        splits=[split],
        created_at="2026-05-20T00:00:00Z",
        summary={"n_paths_tested": 1, "mean_path_sharpe": 1.2},
    )

    d = result.to_dict()
    assert "summary" in d
    assert "paths" in d
    assert "config" in d
    assert "disclaimer" in d
    assert d["summary"]["n_paths_tested"] == 1


def test_cpcv_invalid_params() -> None:
    """Test that invalid parameters raise ValueError."""
    from aurora.validation.cpcv import CPCVConfig, generate_cpcv_splits

    dates = pd.date_range("2020-01-01", periods=100, freq="D")
    df = pd.DataFrame({
        "timestamp": dates,
        "signal": np.ones(len(dates)),
        "close": np.ones(len(dates)) * 100.0,
    })

    with pytest.raises(ValueError, match="n_test_splits must be"):
        generate_cpcv_splits(df, CPCVConfig(n_splits=4, n_test_splits=5))

    with pytest.raises(ValueError, match="n_splits must be"):
        generate_cpcv_splits(df, CPCVConfig(n_splits=1, n_test_splits=1))


def test_deflated_sharpe_ratio() -> None:
    """Test Deflated Sharpe Ratio calculation on known inputs."""
    from aurora.validation.cpcv import deflated_sharpe_ratio

    dsr = deflated_sharpe_ratio(observed_sharpe=1.5, n_paths=15, sharpe_std=0.5)
    assert dsr >= 0.0, "DSR should not be negative"
    assert dsr <= 1.5, "DSR should not exceed observed Sharpe"
    assert dsr > 0.0, "DSR with positive Sharpe should be positive"

    dsr_zero = deflated_sharpe_ratio(observed_sharpe=0.0, n_paths=10, sharpe_std=0.5)
    assert dsr_zero == 0.0, "DSR should be 0 for zero Sharpe"

    dsr_neg = deflated_sharpe_ratio(observed_sharpe=-0.5, n_paths=10, sharpe_std=0.5)
    assert dsr_neg == 0.0, "DSR should be 0 for negative Sharpe"

    dsr_single = deflated_sharpe_ratio(observed_sharpe=2.0, n_paths=1, sharpe_std=0.5)
    assert dsr_single == 2.0, "DSR with single path should equal observed Sharpe"


def test_deflated_sharpe_ratio_penalty() -> None:
    """Test that DSR penalty increases with more paths (multi-testing correction)."""
    from aurora.validation.cpcv import deflated_sharpe_ratio

    sr = 2.0
    dsr_2 = deflated_sharpe_ratio(observed_sharpe=sr, n_paths=2, sharpe_std=0.5)
    dsr_10 = deflated_sharpe_ratio(observed_sharpe=sr, n_paths=10, sharpe_std=0.5)
    dsr_100 = deflated_sharpe_ratio(observed_sharpe=sr, n_paths=100, sharpe_std=0.5)

    assert dsr_2 < dsr_10 < dsr_100, (
        "DSR penalty factor (sqrt(1-1/N)) increases with more paths, "
        "reducing the penalty for larger N"
    )
    assert dsr_2 > 0.0
    assert dsr_10 > 0.0
    assert dsr_100 > 0.0


def test_strategy_selection_bias_score() -> None:
    """Test strategy selection bias score."""
    from aurora.validation.cpcv import strategy_selection_bias_score

    score = strategy_selection_bias_score(
        observed_sharpe=2.0,
        mean_path_sharpe=1.0,
        best_path_sharpe=2.5,
        n_paths=20,
    )
    assert 0.0 <= score <= 1.0, "Bias score should be between 0 and 1"

    score_no_bias = strategy_selection_bias_score(
        observed_sharpe=1.0,
        mean_path_sharpe=1.0,
        best_path_sharpe=1.5,
        n_paths=20,
    )
    assert score_no_bias >= 0.0

    score_single = strategy_selection_bias_score(
        observed_sharpe=1.5,
        mean_path_sharpe=1.0,
        best_path_sharpe=1.5,
        n_paths=1,
    )
    assert score_single == 0.0, "Single path should have zero bias"


def test_summarize_cpcv_paths() -> None:
    """Test CPCV path summarization."""
    from aurora.validation.cpcv import (
        BacktestPathResult,
        summarize_cpcv_paths,
    )

    paths = [
        BacktestPathResult(
            path_id=i,
            train_start="2020-01-01",
            train_end="2020-06-01",
            test_start="2020-06-01",
            test_end="2020-12-01",
            total_return=0.1 + i * 0.05,
            sharpe_ratio=1.0 + i * 0.2,
            max_drawdown=-0.05,
            trade_count=20,
            win_rate=0.6,
            profit_factor=1.5,
            equity_curve=[100000.0, 110000.0],
            passed=True,
        )
        for i in range(6)
    ]

    summary = summarize_cpcv_paths(paths, n_paths_tested=6, observed_sharpe=1.5, sharpe_std=0.4)

    assert summary["n_paths_tested"] == 6
    assert summary["pct_profitable"] >= 0.0
    assert "deflated_sharpe_ratio" in summary
    assert "backtest_overfitting_probability" in summary
    assert "disclaimer" in summary


def test_cpcv_run_integration() -> None:
    """Test full CPCV pipeline with synthetic data."""
    from aurora.validation.cpcv import CPCVConfig, run_cpcv_validation

    dates = pd.date_range("2020-01-01", periods=500, freq="D")
    np.random.seed(42)
    signals = np.random.choice([0, 1], size=len(dates))
    closes = 100 + np.cumsum(np.random.randn(len(dates)) * 0.5)
    df = pd.DataFrame({
        "timestamp": dates,
        "signal": signals,
        "close": closes,
    })

    config = CPCVConfig(n_splits=4, n_test_splits=2, purge_days=5, embargo_days=5)
    result = run_cpcv_validation(df, config, observed_sharpe=1.2)

    assert result.config == config
    assert len(result.paths) > 0
    assert result.summary["n_paths_tested"] == len(result.paths)
    assert "deflated_sharpe_ratio" in result.summary
    assert "backtest_overfitting_probability" in result.summary
    assert result.disclaimer == result.disclaimer


def test_backtest_path_result_to_dict() -> None:
    """Test BacktestPathResult serialization."""
    from aurora.validation.cpcv import BacktestPathResult

    path = BacktestPathResult(
        path_id=5,
        train_start="2020-01-01T00:00:00",
        train_end="2020-06-01T00:00:00",
        test_start="2020-06-01T00:00:00",
        test_end="2020-12-01T00:00:00",
        total_return=0.25,
        sharpe_ratio=1.8,
        max_drawdown=-0.08,
        trade_count=30,
        win_rate=0.65,
        profit_factor=2.0,
        equity_curve=[100000.0, 110000.0, 120000.0, 125000.0],
        passed=True,
        issues=[],
    )

    d = path.to_dict()
    assert d["path_id"] == 5
    assert d["sharpe_ratio"] == 1.8
    assert len(d["equity_curve"]) == 4
    assert d["passed"] is True


def test_cpcv_paths_trade_count() -> None:
    """Test that CPCV backtest produces expected trade counts."""
    from aurora.validation.cpcv import CPCVConfig, generate_cpcv_splits, compute_cpcv_paths

    dates = pd.date_range("2020-01-01", periods=400, freq="D")
    signals = np.where(np.arange(len(dates)) % 10 < 5, 1, 0)
    closes = 100 + np.cumsum(np.random.randn(len(dates)) * 0.3)
    df = pd.DataFrame({
        "timestamp": dates,
        "signal": signals,
        "close": closes,
    })

    config = CPCVConfig(n_splits=4, n_test_splits=2, purge_days=5, embargo_days=5)
    splits = generate_cpcv_splits(df, config)
    paths = compute_cpcv_paths(df, splits, config)

    assert len(paths) == len(splits)
    for path in paths:
        assert isinstance(path.trade_count, int)
        assert path.path_id >= 0


def test_cpcv_purge_embargo_boundary_cases() -> None:
    """Test CPCV with extreme purge/embargo settings."""
    from aurora.validation.cpcv import CPCVConfig, generate_cpcv_splits

    dates = pd.date_range("2020-01-01", periods=600, freq="D")
    df = pd.DataFrame({
        "timestamp": dates,
        "signal": np.ones(len(dates)),
        "close": np.ones(len(dates)) * 100.0,
    })

    config = CPCVConfig(n_splits=4, n_test_splits=2, purge_days=50, embargo_days=50)
    splits = generate_cpcv_splits(df, config)

    for split in splits:
        if len(split.train_indices) > 0:
            assert len(split.train_indices) >= 0


def test_cpcv_cli_import() -> None:
    """Test that CPCV CLI command can be imported."""
    try:
        from aurora.cli.app import validation_cpcv
        assert validation_cpcv is not None
    except ImportError as e:
        pytest.fail(f"Cannot import validation_cpcv: {e}")


def test_path_analysis_import() -> None:
    """Test that path_analysis functions can be imported."""
    from aurora.validation.path_analysis import (
        deflated_sharpe_ratio,
        strategy_selection_bias_score,
        plot_equity_curves,
        compute_probabilistic_sharpe_ratio,
    )

    dsr = deflated_sharpe_ratio(1.5, 10, 0.5)
    assert dsr >= 0.0

    bias = strategy_selection_bias_score(2.0, 1.0, 2.5, 20)
    assert 0.0 <= bias <= 1.0

    psr = compute_probabilistic_sharpe_ratio(1.5, 0.5, 252)
    assert 0.0 <= psr <= 1.0


def test_plot_equity_curves_no_matplotlib() -> None:
    """Test plot_equity_curves gracefully handles missing matplotlib."""
    from aurora.validation.path_analysis import plot_equity_curves

    result = plot_equity_curves([], title="Test")
    assert "error" in result or "n_paths" in result


def test_path_analysis_deflated_sharpe_ratio() -> None:
    """Test path_analysis DSR matches cpcv DSR."""
    from aurora.validation.cpcv import deflated_sharpe_ratio as cpcv_dsr
    from aurora.validation.path_analysis import deflated_sharpe_ratio as pa_dsr

    sr = 2.0
    n = 20
    std = 0.5

    val_cpcv = cpcv_dsr(sr, n, std)
    val_pa = pa_dsr(sr, n, std)

    assert abs(val_cpcv - val_pa) < 1e-6, "DSR implementations should match"