"""Feature Leakage Detector for financial time-series ML pipelines.

Provides static AST-based code analysis and runtime statistical correlation testing
to detect lookahead bias in feature engineering pipelines. Flags forward-looking
features before they corrupt backtest results.

This module is research-only. No live trading, no broker calls.
"""

from __future__ import annotations

import ast
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


MANDATORY_DISCLAIMER = (
    "Feature leakage detection is a research tool. It cannot guarantee the "
    "absence of lookahead bias. Results are not profitability guarantees. "
    "AURORA is research-only. Past performance does not guarantee future results."
)


@dataclass(frozen=True)
class LeakageFlag:
    """Single leakage finding from static or runtime analysis."""

    severity: str
    feature_name: str
    file: str
    line: int | None
    code: str
    description: str
    suggested_fix: str


@dataclass
class FeatureLeakageResult:
    """Leakage result for a single feature."""

    feature: str
    correlation_with_future_label: dict[int, float]
    p_values: dict[int, float]
    max_abs_correlation_beyond_horizon: float
    flagged: bool
    flag_reason: str
    severity: str


@dataclass
class LeakageReport:
    """Full leakage detection report combining static and runtime analysis."""

    verdict: str
    static_findings: list[LeakageFlag]
    runtime_findings: list[FeatureLeakageResult]
    critical_count: int
    warning_count: int
    info_count: int
    per_feature_results: list[dict[str, Any]]
    recommended_actions: list[str]
    disclaimer: str = MANDATORY_DISCLAIMER
    scanned_files: list[str] = field(default_factory=list)
    analyzed_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "static_findings": [asdict(f) for f in self.static_findings],
            "runtime_findings": [asdict(f) for f in self.runtime_findings],
            "critical_count": self.critical_count,
            "warning_count": self.warning_count,
            "info_count": self.info_count,
            "per_feature_results": self.per_feature_results,
            "recommended_actions": self.recommended_actions,
            "disclaimer": self.disclaimer,
            "scanned_files": self.scanned_files,
            "analyzed_at": self.analyzed_at,
        }


VERDICT_CLEAN = "CLEAN"
VERDICT_SUSPECT = "SUSPECT"
VERDICT_COMPROMISED = "COMPROMISED"


class LeakageDetectionError(Exception):
    """Raised when leakage detection itself fails."""


class FeatureLeakageDetector:
    """Detects lookahead bias via static AST analysis and runtime correlation testing."""

    def __init__(
        self,
        files_to_scan: list[str] | None = None,
        p_value_threshold: float = 0.001,
        bonferroni_correction: bool = True,
        correlation_threshold: float = 0.3,
    ) -> None:
        """Initialize the detector.

        Args:
            files_to_scan: List of Python file paths to scan for static analysis.
            p_value_threshold: P-value threshold for runtime flagging.
            bonferroni_correction: Apply Bonferroni correction across features.
            correlation_threshold: Minimum absolute correlation to flag as leakage.
        """
        self.files_to_scan = files_to_scan or []
        self.p_value_threshold = p_value_threshold
        self.bonferroni_correction = bonferroni_correction
        self.correlation_threshold = correlation_threshold

    def scan_feature_file(self, filepath: str) -> list[LeakageFlag]:
        """Scan a Python source file for static leakage patterns.

        Args:
            filepath: Path to Python source file.

        Returns:
            List of LeakageFlag objects for detected issues.
        """
        findings: list[LeakageFlag] = []
        path = Path(filepath)

        if not path.exists():
            return findings

        if path.suffix.lower() in (".csv", ".json", ".txt", ".md", ".yaml", ".yml", ".lock"):
            return findings

        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return findings

        tree = ast.parse(source, filename=str(filepath))

        visitor = _LeakageASTVisitor(filepath)
        visitor.visit(tree)
        findings.extend(visitor.findings)

        return findings

    def scan_all_files(self) -> list[LeakageFlag]:
        """Scan all configured files for static leakage patterns.

        Silently skips files that are not valid Python source (e.g., CSV data files).
        """
        all_findings: list[LeakageFlag] = []
        for filepath in self.files_to_scan:
            findings = self.scan_feature_file(filepath)
            all_findings.extend(findings)
        return all_findings

    def test_feature_independence(
        self,
        feature_df: pd.DataFrame,
        label_series: pd.Series,
        horizon_days: int = 5,
        timestamp_col: str = "timestamp",
    ) -> list[FeatureLeakageResult]:
        """Test whether features are independent of future labels.

        Computes Spearman correlation between each feature at time T and the
        label at T+h for h = 1..horizon_days and beyond. Flags features with
        statistically significant correlation beyond the intended horizon.

        Args:
            feature_df: DataFrame with features as columns, indexed by timestamp.
            label_series: Series with labels as values, indexed by timestamp.
            horizon_days: The intended prediction horizon.
            timestamp_col: Name of the timestamp column.

        Returns:
            List of FeatureLeakageResult, one per feature.
        """
        if not isinstance(feature_df, pd.DataFrame) or feature_df.empty:
            return []
        if not isinstance(label_series, pd.Series) or label_series.empty:
            return []

        common_idx = feature_df.index.intersection(label_series.index)
        if len(common_idx) < 30:
            return []

        _aligned_feat = feature_df.loc[common_idx]
        _aligned_lbl = label_series.loc[common_idx]

        if isinstance(_aligned_feat, pd.DataFrame):
            feature_names = list(_aligned_feat.columns)
        else:
            return []

        max_extended_horizon = max(horizon_days + 5, horizon_days * 2)
        results: list[FeatureLeakageResult] = []

        adjusted_threshold = self.p_value_threshold
        if self.bonferroni_correction and len(feature_names) > 0:
            adjusted_threshold = self.p_value_threshold / len(feature_names)

        for feat in feature_names:
            feat_vals = _aligned_feat[feat].values
            label_vals = _aligned_lbl.values

            valid_mask = ~(np.isnan(feat_vals) | np.isnan(label_vals))
            feat_clean = feat_vals[valid_mask]
            label_clean = label_vals[valid_mask]

            if len(feat_clean) < 20:
                continue

            correlations: dict[int, float] = {}
            p_values: dict[int, float] = {}

            # Start at lag 0 (same bar). A feature that is statistically tied to
            # the *contemporaneous* forward-looking label is using information
            # that would not be available at decision time — classic same-bar
            # label contamination. The previous implementation started at lag 1
            # and only inspected lags strictly beyond the horizon, so same-bar
            # and at-horizon-boundary leakage was never flagged.
            for h in range(0, max_extended_horizon + 1):
                feat_shifted = feat_clean[:-h] if h > 0 else feat_clean
                label_future = label_clean[h:] if h > 0 else label_clean

                if len(feat_shifted) < 10 or len(label_future) < 10:
                    continue

                try:
                    from scipy.stats import spearmanr
                    corr, p_val = spearmanr(feat_shifted, label_future, nan_policy="omit")
                    if not np.isnan(corr):
                        correlations[h] = float(corr)
                        p_values[h] = float(p_val) if p_val is not None else 1.0
                except Exception:
                    pass

            beyond_horizon_corrs = [
                abs(correlations.get(h, 0.0))
                for h in range(horizon_days + 1, max_extended_horizon + 1)
            ]
            max_abs_corr_beyond = max(beyond_horizon_corrs) if beyond_horizon_corrs else 0.0

            flagged = False
            flag_reason = ""
            severity = "INFO"

            # A genuine predictor's correlation with a forward label should DECAY
            # by the time it reaches the intended horizon. We therefore flag
            # significant high correlation in TWO regimes:
            #   (a) within-horizon / at the boundary (lag 0 .. horizon): the
            #       feature appears to already contain the label's information
            #       (same-bar contamination or a label-leaking transform); and
            #   (b) beyond the horizon (lag horizon+1 .. max): correlation that
            #       persists past the prediction horizon also indicates leakage.
            within_lags = range(0, horizon_days + 1)
            beyond_lags = range(horizon_days + 1, max_extended_horizon + 1)

            for regime, lags in (("within-horizon", within_lags), ("beyond-horizon", beyond_lags)):
                for h in lags:
                    p_val = p_values.get(h, 1.0)
                    corr_val = correlations.get(h, 0.0)
                    if p_val < adjusted_threshold and abs(corr_val) > self.correlation_threshold:
                        flagged = True
                        if h == 0:
                            location = "at lag 0 (same-bar contamination)"
                        elif regime == "within-horizon":
                            location = (
                                f"at lag {h} within intended horizon {horizon_days} "
                                "(feature already contains label information)"
                            )
                        else:
                            location = f"at lag {h} beyond intended horizon {horizon_days}"
                        flag_reason = (
                            f"Significant correlation ({corr_val:.3f}, p={p_val:.4f}) "
                            f"{location}"
                        )
                        severity = "CRITICAL"
                        break
                if flagged:
                    break

            results.append(
                FeatureLeakageResult(
                    feature=feat,
                    correlation_with_future_label=correlations,
                    p_values=p_values,
                    max_abs_correlation_beyond_horizon=max_abs_corr_beyond,
                    flagged=flagged,
                    flag_reason=flag_reason,
                    severity=severity,
                )
            )

        return results

    def generate_report(
        self,
        static_findings: list[LeakageFlag] | None = None,
        runtime_findings: list[FeatureLeakageResult] | None = None,
    ) -> LeakageReport:
        """Combine static and runtime findings into a LeakageReport.

        Args:
            static_findings: Findings from static AST analysis.
            runtime_findings: Findings from runtime correlation testing.

        Returns:
            LeakageReport with verdict and aggregated findings.
        """
        static_findings = static_findings or []
        runtime_findings = runtime_findings or []

        critical_count = sum(1 for f in static_findings if f.severity == "CRITICAL")
        critical_count += sum(
            1 for f in runtime_findings if f.severity == "CRITICAL"
        )
        warning_count = sum(1 for f in static_findings if f.severity == "WARNING")
        warning_count += sum(1 for f in runtime_findings if f.severity == "WARNING")
        info_count = sum(1 for f in static_findings if f.severity == "INFO")

        per_feature_results = []
        for f in runtime_findings:
            per_feature_results.append({
                "feature": f.feature,
                "max_abs_correlation_beyond_horizon": f.max_abs_correlation_beyond_horizon,
                "flagged": f.flagged,
                "flag_reason": f.flag_reason,
                "severity": f.severity,
            })

        recommended_actions: list[str] = []
        if critical_count > 0:
            recommended_actions.append(
                "CRITICAL leakage detected. Remove or fix features with forward-looking data "
                "before proceeding. Do not interpret backtest results from compromised features."
            )
        if warning_count > 0:
            recommended_actions.append(
                "WARNING leakage patterns found. Review suggested fixes and re-run detection."
            )
        if not runtime_findings and not static_findings:
            recommended_actions.append(
                "No runtime features tested. Provide feature_df and label_series to run "
                "correlation-based leakage testing."
            )

        if critical_count > 0:
            verdict = VERDICT_COMPROMISED
        elif warning_count > 0:
            verdict = VERDICT_SUSPECT
        else:
            verdict = VERDICT_CLEAN

        return LeakageReport(
            verdict=verdict,
            static_findings=static_findings,
            runtime_findings=runtime_findings,
            critical_count=critical_count,
            warning_count=warning_count,
            info_count=info_count,
            per_feature_results=per_feature_results,
            recommended_actions=recommended_actions,
            scanned_files=self.files_to_scan,
        )


class _LeakageASTVisitor(ast.NodeVisitor):
    """AST visitor that detects lookahead bias patterns in feature code."""

    def __init__(self, filepath: str) -> None:
        self.filepath = filepath
        self.findings: list[LeakageFlag] = []

    def visit_Call(self, node: ast.Call) -> None:
        name = self._get_name(node.func)

        if name in ("shift", "Shift"):
            if node.args:
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, int):
                    if arg.value < 0:
                        self.findings.append(
                            LeakageFlag(
                                severity="CRITICAL",
                                feature_name="shift",
                                file=self.filepath,
                                line=node.lineno or None,
                                code=f"shift({arg.value})",
                                description=(
                                    f"Negative shift({arg.value}) looks forward in time. "
                                    "This introduces lookahead bias."
                                ),
                                suggested_fix=(
                                    f"Use shift({abs(arg.value)}) for a backward shift, "
                                    "or remove this feature if forward data is required."
                                ),
                            )
                        )
                elif isinstance(arg, ast.UnaryOp) and isinstance(arg.op, ast.USub):
                    self.findings.append(
                        LeakageFlag(
                            severity="CRITICAL",
                            feature_name="shift",
                            file=self.filepath,
                            line=node.lineno or None,
                            code="shift(-N)",
                            description="Negative shift looks forward in time.",
                            suggested_fix="Use positive shift for backward look.",
                        )
                    )

        if name in ("rolling", "Rolling"):
            pass

        if name in ("fit_transform", "StandardScaler", "MinMaxScaler"):
            self.findings.append(
                LeakageFlag(
                    severity="CRITICAL",
                    feature_name=name,
                    file=self.filepath,
                    line=node.lineno or None,
                    code=name,
                    description=(
                        f"{name} called on potentially full dataset. "
                        "Fitting scalers before temporal splitting introduces lookahead bias."
                    ),
                    suggested_fix=(
                        "Fit scalers on training set only. Use only .transform() "
                        "on test/validation data. Apply after temporal split."
                    ),
                )
            )

        # Merge/join/concat are everyday DataFrame operations; flagging every
        # one drowns real findings in noise. Only flag a time-axis concat that
        # could interleave future rows: pd.concat(..., axis=0) (the default).
        # Plain column joins/merges and axis=1 concats do not move data across
        # the time axis, so they are not reported.
        if name == "concat":
            axis_is_time = True  # default axis=0 stacks rows along the time axis
            for kw in node.keywords:
                if kw.arg == "axis":
                    if isinstance(kw.value, ast.Constant) and kw.value.value in (1, "columns"):
                        axis_is_time = False
            if axis_is_time:
                self.findings.append(
                    LeakageFlag(
                        severity="INFO",
                        feature_name=name,
                        file=self.filepath,
                        line=node.lineno or None,
                        code=f"{name}(axis=0)",
                        description=(
                            "pd.concat along the time axis (axis=0) detected. If this "
                            "stitches rows together, ensure it happens before the "
                            "temporal split so future rows cannot leak into training."
                        ),
                        suggested_fix=(
                            "Concatenate along the time axis only before temporal "
                            "splitting; slice features and labels independently after."
                        ),
                    )
                )

        # Bare reductions (mean/std/min/max/sum) are only a leak when they
        # collapse the TIME axis of a pandas object without a rolling/expanding/
        # ewm window or a prior shift. Calling such a reduction on the result of
        # .rolling()/.expanding()/.ewm()/.groupby() (or with an explicit
        # axis/window argument) is safe and must NOT be flagged. This removes
        # the previous blanket false positives on `df['x'].rolling(20).mean()`.
        if name in ("mean", "std", "min", "max", "sum") and not node.args:
            if self._is_time_axis_reduction(node):
                self.findings.append(
                    LeakageFlag(
                        severity="WARNING",
                        feature_name=name,
                        file=self.filepath,
                        line=node.lineno or None,
                        code=f"{name}()",
                        description=(
                            f"Global {name}() over the full series without a rolling/"
                            "expanding window. This computes a statistic across the "
                            "entire dataset, including data that is in the future "
                            "relative to a given prediction point."
                        ),
                        suggested_fix=(
                            f"Use rolling(...).{name}() or expanding().{name}() with an "
                            "explicit lookback window so only past data is used."
                        ),
                    )
                )

        self.generic_visit(node)

    _SAFE_WINDOW_METHODS = frozenset(
        {"rolling", "expanding", "ewm", "groupby", "resample", "shift"}
    )

    def _is_time_axis_reduction(self, node: ast.Call) -> bool:
        """Return True only for a bare reduction that collapses the time axis.

        Safe (returns False) when:
          * the reduction has an explicit ``axis`` keyword (caller is explicit),
          * it is chained off a windowing/grouping method
            (rolling/expanding/ewm/groupby/resample) or a prior ``shift``, or
          * the receiver is not an attribute access (e.g. a Python builtin
            ``sum(...)`` on a list, not a pandas reduction).
        """
        # Explicit axis keyword => the author is being deliberate; don't flag.
        for kw in node.keywords:
            if kw.arg == "axis":
                return False

        func = node.func
        if not isinstance(func, ast.Attribute):
            return False  # not obj.mean()-style; likely builtin or unrelated

        # Walk UP the receiver chain looking for a windowing/grouping call such
        # as rolling/expanding/ewm/groupby/resample/shift. Column selection and
        # attribute access between the window and the reduction are transparent,
        # e.g. ``df.groupby('sym')['close'].max()`` is safe even though the
        # immediate receiver of ``.max()`` is a subscript, not the call.
        receiver: ast.AST | None = func.value
        while receiver is not None:
            if isinstance(receiver, ast.Call):
                if self._get_name(receiver.func) in self._SAFE_WINDOW_METHODS:
                    return False
                receiver = receiver.func
            elif isinstance(receiver, ast.Attribute):
                receiver = receiver.value
            elif isinstance(receiver, ast.Subscript):
                receiver = receiver.value
            else:
                break
        return True

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if isinstance(target, ast.Name):
                name = target.id.lower()
                if name in ("x_train", "y_train", "x_test", "y_test", "train_df", "test_df"):
                    if "label" in name:
                        pass

        self.generic_visit(node)

    def _get_name(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        if isinstance(node, ast.Subscript):
            return self._get_name(node.value)
        return ""


def run_leakage_detection(
    feature_df: pd.DataFrame,
    label_series: pd.Series,
    feature_files: list[str] | None = None,
    horizon_days: int = 5,
    p_value_threshold: float = 0.001,
    bonferroni_correction: bool = True,
    correlation_threshold: float = 0.3,
) -> LeakageReport:
    """Convenience function to run full leakage detection.

    Args:
        feature_df: Feature DataFrame indexed by timestamp.
        label_series: Label Series indexed by timestamp.
        feature_files: List of Python feature source files to scan.
        horizon_days: Prediction horizon for runtime testing.
        p_value_threshold: P-value threshold for significance.
        bonferroni_correction: Apply Bonferroni correction across features.
        correlation_threshold: Minimum absolute correlation to flag as leakage.

    Returns:
        LeakageReport with combined static and runtime findings.
    """
    detector = FeatureLeakageDetector(
        files_to_scan=feature_files or [],
        p_value_threshold=p_value_threshold,
        bonferroni_correction=bonferroni_correction,
        correlation_threshold=correlation_threshold,
    )

    static_findings = detector.scan_all_files()
    runtime_findings = detector.test_feature_independence(
        feature_df, label_series, horizon_days
    )

    return detector.generate_report(static_findings, runtime_findings)