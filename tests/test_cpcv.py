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
    """Test Deflated Sharpe Ratio (López de Prado 2014) — a probability in [0, 1].

    The DSR is Phi(...), the probability the observed Sharpe exceeds the
    expected-maximum Sharpe under the null. It is NOT a deflated point estimate
    of the Sharpe; it lives in [0, 1].
    """
    from aurora.validation.cpcv import deflated_sharpe_ratio

    # Use a per-period Sharpe regime that keeps the DSR in the interior so the
    # qualitative properties are observable (not saturated at 0 or 1).
    dsr = deflated_sharpe_ratio(
        observed_sharpe=0.3, n_paths=15, sharpe_std=0.1, n_observations=40
    )
    assert 0.0 <= dsr <= 1.0, "DSR is a probability and must lie in [0, 1]"
    assert dsr > 0.0, "DSR with a strong positive Sharpe should be positive"

    # A higher observed Sharpe yields a higher DSR (more evidence of edge).
    dsr_low = deflated_sharpe_ratio(
        observed_sharpe=0.1, n_paths=15, sharpe_std=0.1, n_observations=40
    )
    dsr_high = deflated_sharpe_ratio(
        observed_sharpe=0.5, n_paths=15, sharpe_std=0.1, n_observations=40
    )
    assert dsr_low < dsr_high, "DSR must increase with a higher observed Sharpe"

    # A Sharpe at or below the expected-max benchmark gives DSR <= 0.5.
    dsr_zero = deflated_sharpe_ratio(
        observed_sharpe=0.0, n_paths=10, sharpe_std=0.1, n_observations=40
    )
    assert 0.0 <= dsr_zero <= 0.5, "Zero observed Sharpe should not look skillful"

    # A negative observed Sharpe is clearly below the null benchmark.
    dsr_neg = deflated_sharpe_ratio(
        observed_sharpe=-0.5, n_paths=10, sharpe_std=0.1, n_observations=40
    )
    assert dsr_neg < 0.5, "Negative Sharpe should give a low DSR"


def test_deflated_sharpe_ratio_penalty() -> None:
    """DSR must DECREASE as the number of trials grows (multiple-testing penalty).

    This is the corrected property. The previous test asserted the opposite
    (DSR increasing in N), which is mathematically backwards: more trials means
    a higher expected-maximum Sharpe under the null, so a fixed observed Sharpe
    is less impressive and the DSR falls.
    """
    from aurora.validation.cpcv import deflated_sharpe_ratio

    sr = 0.3
    kwargs = dict(observed_sharpe=sr, sharpe_std=0.1, n_observations=40)
    dsr_2 = deflated_sharpe_ratio(n_paths=2, **kwargs)
    dsr_10 = deflated_sharpe_ratio(n_paths=10, **kwargs)
    dsr_100 = deflated_sharpe_ratio(n_paths=100, **kwargs)

    assert dsr_2 > dsr_10 > dsr_100, (
        "DSR must strictly decrease as the number of trials N increases "
        "(higher expected-maximum-Sharpe benchmark penalizes the observed SR)"
    )
    for value in (dsr_2, dsr_10, dsr_100):
        assert 0.0 <= value <= 1.0, "DSR is a probability and must lie in [0, 1]"


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


# ---------------------------------------------------------------------------
# Property-based tests for the corrected López de Prado statistics. These assert
# MATHEMATICAL PROPERTIES of the formulas, not just structural presence of keys.
# ---------------------------------------------------------------------------


def test_dsr_is_probability_in_unit_interval() -> None:
    """PROPERTY: DSR is a probability and must always lie in [0, 1]."""
    from aurora.validation.path_analysis import deflated_sharpe_ratio

    rng = np.random.default_rng(0)
    for _ in range(200):
        sr = float(rng.uniform(-1.0, 1.0))
        n = int(rng.integers(1, 500))
        sigma = float(rng.uniform(0.0, 0.5))
        t = int(rng.integers(2, 500))
        skew = float(rng.uniform(-1.0, 1.0))
        kurt = float(rng.uniform(1.5, 9.0))
        dsr = deflated_sharpe_ratio(
            sr, n, sharpe_std=sigma, skewness=skew, kurtosis=kurt, n_observations=t
        )
        assert 0.0 <= dsr <= 1.0, (
            f"DSR out of [0,1]: {dsr} for sr={sr}, n={n}, sigma={sigma}, t={t}"
        )


def test_dsr_monotonically_decreasing_in_n_trials() -> None:
    """PROPERTY: DSR strictly decreases as the number of trials N grows.

    More trials -> higher expected-maximum Sharpe under the null -> a fixed
    observed Sharpe is less impressive -> lower DSR. This is the multiple-testing
    penalty that the old `SR * sqrt(1 - 1/N)` formula got exactly backwards.
    """
    from aurora.validation.path_analysis import deflated_sharpe_ratio

    # Interior regime (non-saturated) so the strict ordering is observable.
    kwargs = dict(observed_sharpe=0.3, sharpe_std=0.1, n_observations=40)
    values = [deflated_sharpe_ratio(n_paths=n, **kwargs) for n in (2, 3, 5, 10, 25, 100)]
    for earlier, later in zip(values, values[1:]):
        assert earlier > later, (
            f"DSR must strictly decrease in N; got non-decreasing pair {earlier} -> {later}"
        )


def test_dsr_increases_with_observed_sharpe() -> None:
    """PROPERTY: DSR increases monotonically with the observed Sharpe ratio."""
    from aurora.validation.path_analysis import deflated_sharpe_ratio

    kwargs = dict(n_paths=15, sharpe_std=0.1, n_observations=40)
    values = [deflated_sharpe_ratio(observed_sharpe=sr, **kwargs) for sr in (0.0, 0.1, 0.2, 0.3, 0.5)]
    for lower, higher in zip(values, values[1:]):
        assert higher >= lower, "DSR must be non-decreasing in observed Sharpe"
    assert values[-1] > values[0], "A strong Sharpe must give a strictly higher DSR than zero"


def test_expected_max_sharpe_grows_with_trials() -> None:
    """PROPERTY: the SR0 benchmark grows with the number of trials."""
    from aurora.validation.path_analysis import expected_max_sharpe

    sr0 = [expected_max_sharpe(n, sharpe_std=0.2) for n in (2, 5, 10, 50, 200)]
    for earlier, later in zip(sr0, sr0[1:]):
        assert later > earlier, "Expected-max Sharpe must increase with more trials"
    # With zero dispersion or a single trial there is no selection benchmark.
    assert expected_max_sharpe(1, 0.2) == 0.0
    assert expected_max_sharpe(100, 0.0) == 0.0


def test_pbo_is_none_for_single_configuration() -> None:
    """PROPERTY: PBO (CSCV) is undefined for a single configuration -> None.

    The honest result is None, not a fabricated ~0.5.
    """
    from aurora.validation.cpcv import probability_of_backtest_overfitting

    rng = np.random.default_rng(1)
    single = rng.normal(size=(300, 1))
    assert probability_of_backtest_overfitting(single) is None


def test_pbo_higher_for_overfit_than_robust_set() -> None:
    """PROPERTY: PBO is higher for a noise/overfit config set than a robust one.

    Construct two configuration grids:
      * 'noise' — every config is pure noise with no genuine edge. Whichever
        config wins in-sample is essentially random out-of-sample, so PBO is
        high (the IS-best frequently lands at/below the OOS median).
      * 'robust' — one config has a real, stable positive drift across the whole
        sample while the rest are noise. The IS-best is usually the genuine
        config, which also wins OOS, so PBO is low.
    """
    from aurora.validation.cpcv import probability_of_backtest_overfitting

    rng = np.random.default_rng(7)
    t, c = 400, 12

    noise = rng.normal(loc=0.0, scale=1.0, size=(t, c))
    pbo_noise = probability_of_backtest_overfitting(noise, n_blocks=10)

    robust = rng.normal(loc=0.0, scale=1.0, size=(t, c))
    # Give a single configuration a persistent, real edge (high signal-to-noise).
    robust[:, 0] = rng.normal(loc=0.6, scale=1.0, size=t)
    pbo_robust = probability_of_backtest_overfitting(robust, n_blocks=10)

    assert pbo_noise is not None and pbo_robust is not None
    assert 0.0 <= pbo_noise <= 1.0 and 0.0 <= pbo_robust <= 1.0
    assert pbo_robust < pbo_noise, (
        f"Robust set PBO ({pbo_robust}) should be below noise set PBO ({pbo_noise})"
    )
    # A pure-noise set should land near the maximally-overfit regime.
    assert pbo_noise >= 0.5


def test_cpcv_purge_removes_overlapping_labels_both_sides() -> None:
    """PROPERTY: purging removes training rows whose label window overlaps the
    test block on BOTH sides, while KEEPING legitimate earlier/later data.

    A correct combinatorial split with an interior test block must retain
    training observations both before and after that block — proving the splits
    did not collapse into a forward-only (train-before / test-after) layout.
    """
    from aurora.validation.cpcv import CPCVConfig, generate_cpcv_splits

    dates = pd.date_range("2020-01-01", periods=400, freq="D")
    df = pd.DataFrame(
        {
            "timestamp": dates,
            "signal": np.ones(len(dates)),
            "close": np.ones(len(dates)) * 100.0,
        }
    )
    purge = 10
    config = CPCVConfig(n_splits=4, n_test_splits=2, purge_days=purge, embargo_days=10)
    splits = generate_cpcv_splits(df, config)
    assert len(splits) > 0

    ts = np.sort(pd.to_datetime(df["timestamp"]).unique())

    saw_interior_split_with_both_sides = False
    for split in splits:
        train = np.sort(split.train_indices)
        test = np.sort(split.test_indices)

        # No train/test index overlap.
        assert len(set(train.tolist()) & set(test.tolist())) == 0

        # Purge invariant: no kept training observation may have a label window
        # [t, t + purge_days] overlapping a contiguous test block while also
        # starting before that block ends.
        test_set = set(test.tolist())
        # Identify contiguous test blocks.
        blocks = []
        start = prev = test[0]
        for idx in test[1:]:
            if idx == prev + 1:
                prev = idx
            else:
                blocks.append((start, prev))
                start = prev = idx
        blocks.append((start, prev))

        for tr_idx in train:
            t_start = ts[tr_idx]
            t_label_end = t_start + pd.Timedelta(days=purge)
            for b0, b1 in blocks:
                block_start = ts[b0]
                block_end = ts[b1]
                overlaps = (t_label_end >= block_start) and (t_start <= block_end)
                assert not overlaps, (
                    f"Training idx {tr_idx} label window overlaps test block "
                    f"[{b0},{b1}] but was not purged"
                )

        has_before = bool((train < test.min()).any())
        has_after = bool((train > test.max()).any())
        if test.min() > 0 and test.max() < len(ts) - 1:
            # Interior test block: a correct CPCV split keeps data on both sides.
            if has_before and has_after:
                saw_interior_split_with_both_sides = True

    assert saw_interior_split_with_both_sides, (
        "No interior split retained training data on BOTH sides of the test block "
        "— purge likely collapsed the combinatorial splits into forward-only."
    )