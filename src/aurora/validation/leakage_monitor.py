"""Leakage Monitor for automatic feature leakage detection in research runs.

Wraps the FeatureLeakageDetector and runs automatically as part of every
research run workflow. Blocks compromised runs, warns on suspect runs,
and records clean verdicts in the manifest.

This module is research-only. No live trading, no broker calls.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd


MANDATORY_DISCLAIMER = (
    "Feature leakage detection is a research tool. It cannot guarantee the "
    "absence of lookahead bias. Results are not profitability guarantees. "
    "AURORA is research-only. Past performance does not guarantee future results."
)


class LeakageError(Exception):
    """Raised when feature leakage is detected at CRITICAL severity."""


class LeakageMonitor:
    """Automatic leakage detection monitor for research runs."""

    def __init__(
        self,
        run_dir: str,
        feature_df: pd.DataFrame | None = None,
        label_series: pd.Series | None = None,
        feature_files: list[str] | None = None,
        horizon_days: int = 5,
        block_on_compromised: bool = True,
        warn_on_suspect: bool = True,
        p_value_threshold: float = 0.001,
        bonferroni_correction: bool = True,
        correlation_threshold: float = 0.3,
    ) -> None:
        """Initialize the leakage monitor.

        Args:
            run_dir: Directory for this research run.
            feature_df: Feature DataFrame for runtime testing.
            label_series: Label Series for runtime testing.
            feature_files: Python source files for static analysis.
            horizon_days: Prediction horizon for correlation testing.
            block_on_compromised: Raise LeakageError if verdict is COMPROMISED.
            warn_on_suspect: Add warning to manifest if verdict is SUSPECT.
            p_value_threshold: P-value threshold for significance.
            bonferroni_correction: Apply Bonferroni correction across features.
            correlation_threshold: Minimum correlation to flag as leakage.
        """
        self.run_dir = Path(run_dir)
        self.feature_df = feature_df
        self.label_series = label_series
        self.feature_files = feature_files or []
        self.horizon_days = horizon_days
        self.block_on_compromised = block_on_compromised
        self.warn_on_suspect = warn_on_suspect
        self.p_value_threshold = p_value_threshold
        self.bonferroni_correction = bonferroni_correction
        self.correlation_threshold = correlation_threshold
        self._report: dict[str, Any] | None = None

    def run(self) -> dict[str, Any]:
        """Run leakage detection and write report to run directory.

        Returns:
            Leakage report dictionary.

        Raises:
            LeakageError: If verdict is COMPROMISED and block_on_compromised is True.
        """
        from aurora.validation.leakage_detector import (
            FeatureLeakageDetector,
            LeakageReport,
            VERDICT_CLEAN,
            VERDICT_COMPROMISED,
            VERDICT_SUSPECT,
            run_leakage_detection,
        )

        detector = FeatureLeakageDetector(
            files_to_scan=self.feature_files,
            p_value_threshold=self.p_value_threshold,
            bonferroni_correction=self.bonferroni_correction,
            correlation_threshold=self.correlation_threshold,
        )

        static_findings: list[Any] = []
        runtime_findings: list[Any] = []

        if self.feature_files:
            static_findings = detector.scan_all_files()

        if self.feature_df is not None and self.label_series is not None:
            runtime_findings = detector.test_feature_independence(
                self.feature_df,
                self.label_series,
                self.horizon_days,
            )

        report = detector.generate_report(static_findings, runtime_findings)

        report_dict = report.to_dict()

        report_path = self.run_dir / "leakage_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with report_path.open("w", encoding="utf-8") as f:
            json.dump(report_dict, f, indent=2, default=str)

        self._report = report_dict

        manifest_path = self.run_dir / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["leakage_verdict"] = report.verdict
            manifest["leakage_verified"] = report.verdict == VERDICT_CLEAN
            manifest["leakage_analyzed_at"] = report.analyzed_at
            manifest["leakage_report_path"] = str(report_path)

            if report.verdict == VERDICT_COMPROMISED:
                manifest["safety_flags"] = manifest.get("safety_flags", {})
                manifest["safety_flags"]["leakage_detected"] = True
                manifest["safety_flags"]["placed_orders"] = False
                manifest["safety_flags"]["used_broker"] = False
                manifest["safety_flags"]["research_only"] = True
                manifest["safety_flags"]["external_llm_calls"] = False
                manifest["leakage_disclaimer"] = MANDATORY_DISCLAIMER
            elif report.verdict == VERDICT_SUSPECT:
                manifest.setdefault("leakage_warnings", []).append(
                    f"{report.critical_count} critical, {report.warning_count} warnings found"
                )

            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        if report.verdict == VERDICT_COMPROMISED and self.block_on_compromised:
            raise LeakageError(
                f"Feature leakage detected (COMPROMISED verdict). "
                f"Critical: {report.critical_count}, Warnings: {report.warning_count}. "
                f"Results are invalid. {MANDATORY_DISCLAIMER}"
            )

        return report_dict

    def verdict(self) -> str:
        """Get the current verdict if a report exists."""
        if self._report is not None:
            return self._report.get("verdict", "UNKNOWN")
        return "NOT_RUN"


def check_leakage_for_run(
    run_dir: str,
    feature_df: pd.DataFrame | None = None,
    label_series: pd.Series | None = None,
    feature_files: list[str] | None = None,
    horizon_days: int = 5,
    p_value_threshold: float = 0.001,
    bonferroni_correction: bool = True,
    correlation_threshold: float = 0.3,
) -> dict[str, Any]:
    """Check feature leakage for a research run.

    Args:
        run_dir: Research run directory.
        feature_df: Feature DataFrame for runtime testing.
        label_series: Label Series for runtime testing.
        feature_files: Python feature source files for static scanning.
        horizon_days: Prediction horizon.
        p_value_threshold: P-value threshold for significance.
        bonferroni_correction: Apply Bonferroni correction.
        correlation_threshold: Minimum correlation to flag as leakage.

    Returns:
        Leakage report dictionary.

    Raises:
        LeakageError: If verdict is COMPROMISED.
    """
    monitor = LeakageMonitor(
        run_dir=run_dir,
        feature_df=feature_df,
        label_series=label_series,
        feature_files=feature_files,
        horizon_days=horizon_days,
        p_value_threshold=p_value_threshold,
        bonferroni_correction=bonferroni_correction,
        correlation_threshold=correlation_threshold,
    )
    return monitor.run()


def load_leakage_report(run_dir: str) -> dict[str, Any] | None:
    """Load an existing leakage report from a research run directory."""
    path = Path(run_dir) / "leakage_report.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def leakage_verdict_to_review_finding(
    verdict: str,
    critical_count: int,
    warning_count: int,
) -> dict[str, Any]:
    """Convert leakage verdict into a review board finding dict.

    Args:
        verdict: CLEAN, SUSPECT, or COMPROMISED.
        critical_count: Number of critical static/runtime findings.
        warning_count: Number of warning findings.

    Returns:
        Finding dictionary for the ReviewBoard.
    """
    from aurora.review.board import REVIEW_CRITICAL, REVIEW_WARNING, REVIEW_INFO

    if verdict == "COMPROMISED":
        return {
            "code": "feature_leakage_compromised",
            "severity": REVIEW_CRITICAL,
            "message": (
                "Feature leakage detected — results invalid. "
                f"{critical_count} critical, {warning_count} warnings. "
                f"{MANDATORY_DISCLAIMER}"
            ),
        }
    elif verdict == "SUSPECT":
        return {
            "code": "feature_leakage_suspect",
            "severity": REVIEW_WARNING,
            "message": (
                f"Feature leakage investigation recommended. "
                f"{warning_count} warnings found. Review leakage_report.json."
            ),
        }
    else:
        return {
            "code": "feature_leakage_verified_clean",
            "severity": REVIEW_INFO,
            "message": "Feature leakage detection passed (CLEAN verdict).",
        }