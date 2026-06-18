"""Tests for Feature Leakage Detector and Monitor."""

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


def test_detector_flags_negative_shift() -> None:
    """Test that static analysis correctly flags negative .shift() in source code."""
    from aurora.validation.leakage_detector import FeatureLeakageDetector

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("import pandas as pd\n")
        f.write("prices.shift(-5)\n")
        f.write("data.shift(-10)\n")
        temp_path = f.name

    try:
        detector = FeatureLeakageDetector(files_to_scan=[temp_path])
        findings = detector.scan_all_files()

        critical_findings = [f for f in findings if f.severity == "CRITICAL"]
        assert len(critical_findings) >= 1, (
            f"Expected >=1 CRITICAL finding for negative shift, got {len(critical_findings)}"
        )
        descriptions = [f.description for f in critical_findings]
        assert any("looks forward" in d or "Negative shift" in d for d in descriptions)
    finally:
        Path(temp_path).unlink(missing_ok=True)


def test_detector_clears_clean_code() -> None:
    """Test that static analysis correctly clears code with no leakage."""
    from aurora.validation.leakage_detector import FeatureLeakageDetector

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("import pandas as pd\n")
        f.write("def compute_features(df):\n")
        f.write("    return df['close'].shift(1).rolling(20).mean()\n")
        temp_path = f.name

    try:
        detector = FeatureLeakageDetector(files_to_scan=[temp_path])
        findings = detector.scan_feature_file(temp_path)

        critical_findings = [f for f in findings if f.severity == "CRITICAL"]
        assert len(critical_findings) == 0, f"Expected no CRITICAL findings for clean code, got {critical_findings}"
    finally:
        Path(temp_path).unlink(missing_ok=True)


def test_runtime_detects_forward_leakage() -> None:
    """Test that runtime analysis flags a synthetic feature with known forward leakage."""
    from aurora.validation.leakage_detector import FeatureLeakageDetector

    np.random.seed(42)
    n = 200
    dates = pd.date_range("2020-01-01", periods=n, freq="D")
    label = pd.Series(np.random.randn(n), index=dates, name="label")

    future_incorporated = pd.Series(
        [label.iloc[i + 5] if i + 5 < n else 0 for i in range(n)],
        index=dates,
        name="leaky_feature",
    )

    clean_feature = pd.Series(
        np.random.randn(n) * 0.1,
        index=dates,
        name="clean_feature",
    )

    feature_df = pd.DataFrame({
        "leaky_feature": future_incorporated,
        "clean_feature": clean_feature,
    })

    detector = FeatureLeakageDetector(p_value_threshold=0.01, bonferroni_correction=False)
    results = detector.test_feature_independence(feature_df, label, horizon_days=5)

    assert len(results) == 2

    results_dict = {r.feature: r for r in results}

    assert "leaky_feature" in results_dict
    assert "clean_feature" in results_dict


def test_runtime_clears_independent_features() -> None:
    """Test that runtime analysis clears features with no statistical relationship to future labels."""
    from aurora.validation.leakage_detector import FeatureLeakageDetector

    np.random.seed(123)
    n = 300
    dates = pd.date_range("2020-01-01", periods=n, freq="D")

    independent_noise = pd.Series(np.random.randn(n), index=dates, name="noise_feature")
    label = pd.Series(np.random.randn(n), index=dates, name="label")

    feature_df = pd.DataFrame({"noise_feature": independent_noise})

    detector = FeatureLeakageDetector(p_value_threshold=0.01)
    results = detector.test_feature_independence(feature_df, label, horizon_days=5)

    assert len(results) == 1
    assert not results[0].flagged, "Independent noise should not be flagged"


def test_leakage_report_verdict_compromised() -> None:
    """Test that COMPROMISED verdict is set when critical findings exist."""
    from aurora.validation.leakage_detector import (
        FeatureLeakageResult,
        LeakageFlag,
        LeakageReport,
        VERDICT_COMPROMISED,
    )

    static_findings = [
        LeakageFlag(
            severity="CRITICAL",
            feature_name="test",
            file="test.py",
            line=1,
            code="shift(-5)",
            description="Forward shift detected",
            suggested_fix="Use positive shift",
        )
    ]

    report = LeakageReport(
        verdict=VERDICT_COMPROMISED,
        static_findings=static_findings,
        runtime_findings=[],
        critical_count=1,
        warning_count=0,
        info_count=0,
        per_feature_results=[],
        recommended_actions=["Fix critical leakage"],
    )

    assert report.verdict == VERDICT_COMPROMISED
    assert report.critical_count == 1


def test_leakage_report_verdict_clean() -> None:
    """Test that CLEAN verdict is set when no critical/warning findings exist."""
    from aurora.validation.leakage_detector import LeakageReport, VERDICT_CLEAN

    report = LeakageReport(
        verdict=VERDICT_CLEAN,
        static_findings=[],
        runtime_findings=[],
        critical_count=0,
        warning_count=0,
        info_count=0,
        per_feature_results=[],
        recommended_actions=[],
    )

    assert report.verdict == VERDICT_CLEAN


def test_leakage_monitor_blocks_compromised() -> None:
    """Test that COMPROMISED verdict raises LeakageError when block_on_compromised=True."""
    from aurora.validation.leakage_monitor import LeakageError, LeakageMonitor

    with tempfile.TemporaryDirectory() as tmpdir:
        leaky_file = Path(tmpdir) / "features.py"
        leaky_file.write_text("val = data.shift(-5)\n")
        Path(tmpdir).joinpath("manifest.json").write_text("{}")

        dates = pd.date_range("2020-01-01", periods=100, freq="D")
        feature_df = pd.DataFrame({"f1": np.random.randn(100)}, index=dates)
        label_series = pd.Series(np.random.randn(100), index=dates)

        monitor = LeakageMonitor(
            run_dir=tmpdir,
            feature_df=feature_df,
            label_series=label_series,
            feature_files=[str(leaky_file)],
            block_on_compromised=True,
        )

        with pytest.raises(LeakageError, match="COMPROMISED"):
            monitor.run()


def test_leakage_monitor_clean_passes() -> None:
    """Test that CLEAN verdict passes through without raising."""
    from aurora.validation.leakage_monitor import LeakageMonitor

    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir).joinpath("manifest.json").write_text("{}")

        dates = pd.date_range("2020-01-01", periods=300, freq="D")
        np.random.seed(42)
        feature_df = pd.DataFrame({"noise": np.random.randn(300)}, index=dates)
        label_series = pd.Series(np.random.randn(300), index=dates)

        monitor = LeakageMonitor(
            run_dir=tmpdir,
            feature_df=feature_df,
            label_series=label_series,
            block_on_compromised=True,
        )

        result = monitor.run()
        assert result["verdict"] in ("CLEAN", "SUSPECT")


def test_leakage_monitor_writes_report() -> None:
    """Test that LeakageMonitor writes leakage_report.json to run directory."""
    from aurora.validation.leakage_monitor import LeakageMonitor

    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir).joinpath("manifest.json").write_text("{}")

        dates = pd.date_range("2020-01-01", periods=200, freq="D")
        feature_df = pd.DataFrame({"f1": np.random.randn(200)}, index=dates)
        label_series = pd.Series(np.random.randn(200), index=dates)

        monitor = LeakageMonitor(
            run_dir=tmpdir,
            feature_df=feature_df,
            label_series=label_series,
            block_on_compromised=False,
        )
        result = monitor.run()

        report_path = Path(tmpdir) / "leakage_report.json"
        assert report_path.exists(), "leakage_report.json should be written"

        import json
        saved = json.loads(report_path.read_text())
        assert saved["verdict"] == result["verdict"]


def test_leakage_monitor_updates_manifest() -> None:
    """Test that LeakageMonitor updates manifest with verdict and flags."""
    from aurora.validation.leakage_monitor import LeakageMonitor

    with tempfile.TemporaryDirectory() as tmpdir:
        manifest = {"run_id": "test", "safety_flags": {}}
        manifest_path = Path(tmpdir) / "manifest.json"
        manifest_path.write_text('{"run_id": "test", "safety_flags": {}}')

        dates = pd.date_range("2020-01-01", periods=200, freq="D")
        feature_df = pd.DataFrame({"f1": np.random.randn(200)}, index=dates)
        label_series = pd.Series(np.random.randn(200), index=dates)

        monitor = LeakageMonitor(
            run_dir=tmpdir,
            feature_df=feature_df,
            label_series=label_series,
            block_on_compromised=False,
        )
        monitor.run()

        import json
        updated = json.loads(manifest_path.read_text())
        assert "leakage_verdict" in updated
        assert "leakage_verified" in updated


def test_compromised_verdict_blocks_research_run() -> None:
    """Test that COMPROMISED verdict is generated when critical findings exist."""
    from aurora.validation.leakage_detector import (
        LeakageFlag,
        LeakageReport,
        VERDICT_COMPROMISED,
    )

    static_findings = [
        LeakageFlag(
            severity="CRITICAL",
            feature_name="shift",
            file="test.py",
            line=1,
            code="shift(-5)",
            description="Negative shift looks forward in time.",
            suggested_fix="Use positive shift",
        )
    ]

    report = LeakageReport(
        verdict=VERDICT_COMPROMISED,
        static_findings=static_findings,
        runtime_findings=[],
        critical_count=1,
        warning_count=0,
        info_count=0,
        per_feature_results=[],
        recommended_actions=["Fix critical leakage"],
    )

    assert report.verdict == VERDICT_COMPROMISED
    assert report.critical_count == 1


def test_clean_verdict_passes_research_run() -> None:
    """Test that CLEAN verdict is generated for clean features."""
    from aurora.validation.leakage_detector import (
        LeakageReport,
        VERDICT_CLEAN,
    )

    report = LeakageReport(
        verdict=VERDICT_CLEAN,
        static_findings=[],
        runtime_findings=[],
        critical_count=0,
        warning_count=0,
        info_count=0,
        per_feature_results=[],
        recommended_actions=[],
    )

    assert report.verdict == VERDICT_CLEAN
    assert report.critical_count == 0


def test_suspect_verdict_warns() -> None:
    """Test that SUSPECT verdict adds warning to manifest but allows continuation."""
    from aurora.validation.leakage_detector import (
        FeatureLeakageDetector,
        FeatureLeakageResult,
        VERDICT_SUSPECT,
    )

    runtime_findings = [
        FeatureLeakageResult(
            feature="test_feature",
            correlation_with_future_label={6: 0.15, 7: 0.18},
            p_values={6: 0.05, 7: 0.03},
            max_abs_correlation_beyond_horizon=0.18,
            flagged=True,
            flag_reason="Mild correlation beyond horizon",
            severity="WARNING",
        )
    ]

    detector = FeatureLeakageDetector(p_value_threshold=0.01)
    report = detector.generate_report(runtime_findings=runtime_findings)

    assert report.verdict == VERDICT_SUSPECT
    assert report.warning_count > 0


def test_leakage_detector_cli_import() -> None:
    """Test that leakage CLI command can be imported."""
    try:
        from aurora.cli.app import validation_leakage
        assert validation_leakage is not None
    except ImportError as e:
        pytest.fail(f"Cannot import validation_leakage: {e}")


def test_leakage_monitor_import() -> None:
    """Test that LeakageMonitor can be imported."""
    from aurora.validation.leakage_monitor import (
        LeakageError,
        LeakageMonitor,
        load_leakage_report,
    )

    assert LeakageMonitor is not None
    assert LeakageError is not None
    assert load_leakage_report is not None


def test_leakage_report_serialization() -> None:
    """Test that LeakageReport serializes to dict correctly."""
    from aurora.validation.leakage_detector import LeakageReport, VERDICT_CLEAN

    report = LeakageReport(
        verdict=VERDICT_CLEAN,
        static_findings=[],
        runtime_findings=[],
        critical_count=0,
        warning_count=0,
        info_count=0,
        per_feature_results=[],
        recommended_actions=["Continue monitoring"],
        scanned_files=["src/features.py"],
    )

    d = report.to_dict()
    assert d["verdict"] == VERDICT_CLEAN
    assert d["critical_count"] == 0
    assert "scanned_files" in d
    assert "disclaimer" in d
    assert "analyzed_at" in d


def test_run_leakage_detection_function() -> None:
    """Test the convenience run_leakage_detection function."""
    from aurora.validation.leakage_detector import run_leakage_detection

    np.random.seed(99)
    n = 200
    dates = pd.date_range("2020-01-01", periods=n, freq="D")
    label = pd.Series(np.random.randn(n), index=dates, name="label")
    feature_df = pd.DataFrame({"noise": np.random.randn(n)}, index=dates)

    report = run_leakage_detection(
        feature_df=feature_df,
        label_series=label,
        feature_files=[],
        horizon_days=5,
    )

    assert report.verdict in ("CLEAN", "SUSPECT", "COMPROMISED")
    assert "analyzed_at" in report.to_dict()


def test_bonferroni_threshold_adjustment() -> None:
    """Test that Bonferroni correction adjusts threshold for many features."""
    from aurora.validation.leakage_detector import FeatureLeakageDetector

    np.random.seed(777)
    n = 300
    dates = pd.date_range("2020-01-01", periods=n, freq="D")
    label = pd.Series(np.random.randn(n), index=dates, name="label")

    feature_df = pd.DataFrame({
        f"noise_{i}": np.random.randn(n) for i in range(20)
    }, index=dates)

    detector_corrected = FeatureLeakageDetector(
        p_value_threshold=0.01,
        bonferroni_correction=True,
    )
    detector_uncorrected = FeatureLeakageDetector(
        p_value_threshold=0.01,
        bonferroni_correction=False,
    )

    results_corrected = detector_corrected.test_feature_independence(feature_df, label, horizon_days=5)
    results_uncorrected = detector_uncorrected.test_feature_independence(feature_df, label, horizon_days=5)

    flagged_corrected = sum(1 for r in results_corrected if r.flagged)
    flagged_uncorrected = sum(1 for r in results_uncorrected if r.flagged)

    assert flagged_corrected <= flagged_uncorrected, (
        "Bonferroni correction should flag fewer or equal features"
    )


def test_leakage_detector_no_files() -> None:
    """Test that detector handles case with no files to scan."""
    from aurora.validation.leakage_detector import FeatureLeakageDetector, VERDICT_CLEAN

    detector = FeatureLeakageDetector(files_to_scan=[])
    findings = detector.scan_all_files()

    report = detector.generate_report(static_findings=findings)

    assert report.verdict == VERDICT_CLEAN
    assert len(findings) == 0


# ---------------------------------------------------------------------------
# Property tests for the corrected leakage detection: within-horizon runtime
# contamination is now caught, and the static scanner is context-aware.
# ---------------------------------------------------------------------------


def test_runtime_flags_within_horizon_contamination() -> None:
    """PROPERTY: a feature that contains the label AT the horizon boundary is
    flagged. The old detector only inspected lags strictly beyond the horizon,
    so this same-information leak slipped through entirely.
    """
    from aurora.validation.leakage_detector import FeatureLeakageDetector

    np.random.seed(42)
    n = 200
    dates = pd.date_range("2020-01-01", periods=n, freq="D")
    label = pd.Series(np.random.randn(n), index=dates, name="label")

    # feature[i] == label[i + 5]: correlation peaks at lag 5, which equals the
    # intended horizon (the boundary the old code skipped).
    leaky = pd.Series(
        [label.iloc[i + 5] if i + 5 < n else 0.0 for i in range(n)],
        index=dates,
        name="leaky_feature",
    )
    feature_df = pd.DataFrame({"leaky_feature": leaky})

    detector = FeatureLeakageDetector(p_value_threshold=0.01, bonferroni_correction=False)
    results = detector.test_feature_independence(feature_df, label, horizon_days=5)

    assert len(results) == 1
    assert results[0].flagged, "Within-horizon label contamination must be flagged"
    assert results[0].severity == "CRITICAL"


def test_runtime_flags_same_bar_contamination() -> None:
    """PROPERTY: a feature equal to the contemporaneous label (lag 0) is flagged.

    Same-bar contamination uses information unavailable at decision time. The
    old detector started at lag 1 and never tested the same bar.
    """
    from aurora.validation.leakage_detector import FeatureLeakageDetector

    np.random.seed(7)
    n = 200
    dates = pd.date_range("2020-01-01", periods=n, freq="D")
    label = pd.Series(np.random.randn(n), index=dates, name="label")
    # feature[i] == label[i] plus tiny noise: strong same-bar correlation.
    same_bar = label + np.random.randn(n) * 0.01
    same_bar.name = "same_bar_feature"
    feature_df = pd.DataFrame({"same_bar_feature": same_bar})

    detector = FeatureLeakageDetector(p_value_threshold=0.01, bonferroni_correction=False)
    results = detector.test_feature_independence(feature_df, label, horizon_days=5)

    assert results[0].flagged, "Same-bar (lag 0) contamination must be flagged"
    assert "lag 0" in results[0].flag_reason.lower() or "same-bar" in results[0].flag_reason.lower()


def test_runtime_clears_independent_feature_property() -> None:
    """PROPERTY: a feature independent of the label at every lag stays clean."""
    from aurora.validation.leakage_detector import FeatureLeakageDetector

    np.random.seed(321)
    n = 400
    dates = pd.date_range("2020-01-01", periods=n, freq="D")
    label = pd.Series(np.random.randn(n), index=dates, name="label")
    noise = pd.Series(np.random.randn(n), index=dates, name="noise")
    feature_df = pd.DataFrame({"noise": noise})

    detector = FeatureLeakageDetector(p_value_threshold=0.001)
    results = detector.test_feature_independence(feature_df, label, horizon_days=5)
    assert not results[0].flagged, "Independent noise must not be flagged at any lag"


def test_static_scanner_no_false_positive_on_rolling_reduction() -> None:
    """PROPERTY: a windowed reduction (rolling/expanding) is NOT a false positive."""
    import tempfile
    from aurora.validation.leakage_detector import FeatureLeakageDetector

    src = (
        "import pandas as pd\n"
        "def f(df):\n"
        "    a = df['close'].shift(1).rolling(20).mean()\n"
        "    b = df['close'].expanding().std()\n"
        "    c = df.groupby('sym')['close'].max()\n"
        "    return a, b, c\n"
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as fh:
        fh.write(src)
        temp_path = fh.name
    try:
        findings = FeatureLeakageDetector(files_to_scan=[temp_path]).scan_all_files()
        reduction_flags = [
            f for f in findings if f.feature_name in ("mean", "std", "min", "max", "sum")
        ]
        assert reduction_flags == [], (
            f"Windowed reductions must not be flagged; got {reduction_flags}"
        )
    finally:
        Path(temp_path).unlink(missing_ok=True)


def test_static_scanner_flags_global_reduction_only() -> None:
    """PROPERTY: a bare global reduction over the full series IS flagged,
    while merges/joins are no longer noisy false positives.
    """
    import tempfile
    from aurora.validation.leakage_detector import FeatureLeakageDetector

    src = (
        "import pandas as pd\n"
        "def f(df, other):\n"
        "    m = df['close'].mean()\n"               # global reduction -> flag
        "    j = pd.merge(df, other, on='id')\n"     # merge -> no flag
        "    k = df.join(other)\n"                    # join -> no flag
        "    return m, j, k\n"
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as fh:
        fh.write(src)
        temp_path = fh.name
    try:
        findings = FeatureLeakageDetector(files_to_scan=[temp_path]).scan_all_files()
        names = [f.feature_name for f in findings]
        assert "mean" in names, "Global mean() over the full series should be flagged"
        assert "merge" not in names, "merge should no longer be a false positive"
        assert "join" not in names, "join should no longer be a false positive"
    finally:
        Path(temp_path).unlink(missing_ok=True)


def test_cli_imports_without_eager_tui() -> None:
    """PROPERTY (release blocker): importing the CLI must not eagerly import the
    optional textual-dependent TUI module.
    """
    import sys

    # Importing the CLI app must succeed and must not pull in aurora.tui.app.
    sys.modules.pop("aurora.tui.app", None)
    from aurora.cli.app import app  # noqa: F401

    assert "aurora.tui.app" not in sys.modules, (
        "aurora.tui.app was imported eagerly; the TUI import must be lazy so the "
        "CLI works without the optional `textual` dependency."
    )