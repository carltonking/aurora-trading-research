"""Deterministic review board for completed research runs."""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from aurora.reporting.reports import save_json_report

REVIEW_REJECTED = "REJECTED"
REVIEW_NEEDS_MORE_RESEARCH = "NEEDS_MORE_RESEARCH"
REVIEW_APPROVED_FOR_PAPER_SIMULATION = "APPROVED_FOR_PAPER_SIMULATION"

REVIEW_INFO = "INFO"
REVIEW_WARNING = "WARNING"
REVIEW_CRITICAL = "CRITICAL"

_REQUIRED_SAFETY_FLAGS = {
    "research_only": True,
    "placed_orders": False,
    "used_broker": False,
    "wrote_ledger": False,
    "external_llm_calls": False,
}
_PROFIT_GUARANTEE_PHRASES = [
    "guaranteed profit",
    "risk-free",
    "sure thing",
    "cannot lose",
    "guaranteed return",
]
_DIAGNOSTIC_WARNING_CODES = {
    "walk_forward_failed",
    "high_sharpe_ratio",
    "high_profit_factor",
    "positive_return_low_exposure",
    "single_trade_pnl_concentration",
    "single_period_return_concentration",
    "single_window_return_concentration",
    "low_window_pass_rate",
    "low_walk_forward_trade_count",
    "low_trade_count",
    "cpcv_overfitting_probability",
    "cpcv_deflated_sharpe_ratio_low",
}


@dataclass(frozen=True)
class ReviewFinding:
    """Single deterministic review finding."""

    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class ReviewBoardConfig:
    """Configuration for reviewing a completed research run."""

    run_dir: str
    output_path: str | None = None
    min_trades: int = 50
    max_drawdown_pct: float = 0.25
    min_walk_forward_windows: int = 3
    require_manifest_safety_flags: bool = True
    require_diagnostics: bool = True
    allow_paper_simulation_approval: bool = True
    cpcv_overfitting_threshold: float = 0.5
    cpcv_deflated_sharpe_threshold: float = 0.5


@dataclass(frozen=True)
class ReviewBoardResult:
    """Decision artifact produced by the local review board."""

    run_id: str
    strategy_id: str
    status: str
    reviewed_at: str
    findings: list[ReviewFinding]
    metrics: dict[str, Any]
    diagnostics_summary: dict[str, Any]
    manifest_path: str
    backtest_path: str | None
    diagnostics_path: str | None
    output_path: str | None
    safety_flags: dict[str, Any]


class ReviewBoardError(Exception):
    """Raised when a research run cannot be reviewed."""


def review_research_run(config: ReviewBoardConfig) -> ReviewBoardResult:
    """Review completed research artifacts without running research steps."""
    run_dir = Path(config.run_dir)
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        raise ReviewBoardError(f"Research run manifest not found: {manifest_path}")

    manifest = _load_json(manifest_path)
    findings: list[ReviewFinding] = []
    safety_flags = _safe_dict(manifest.get("safety_flags"))
    if config.require_manifest_safety_flags:
        findings.extend(_safety_flag_findings(safety_flags))

    backtest_path = _artifact_path(manifest, run_dir, "backtest", "backtest.json")
    backtest = _load_optional_json(backtest_path, findings, "missing_backtest", REVIEW_CRITICAL)
    metrics = _extract_metrics(backtest, manifest, findings)
    findings.extend(_metric_findings(metrics, config))

    diagnostics_path = _artifact_path(manifest, run_dir, "diagnostics", "diagnostics.json")
    diagnostics_severity = REVIEW_CRITICAL if config.require_diagnostics else REVIEW_WARNING
    diagnostics = _load_optional_json(
        diagnostics_path,
        findings,
        "missing_diagnostics",
        diagnostics_severity,
    )
    diagnostics_summary = _extract_diagnostics_summary(diagnostics)
    findings.extend(_diagnostic_findings(diagnostics, diagnostics_summary, config))

    report_path = _artifact_path(manifest, run_dir, "report", "report.md")
    findings.extend(_report_language_findings(report_path))

    cpcv_path = _artifact_path(manifest, run_dir, "cpcv", "cpcv_report.json")
    findings.extend(_cpcv_findings(cpcv_path, config))

    leakage_path = run_dir / "leakage_report.json"
    findings.extend(_leakage_findings(leakage_path))

    status = _decide_status(findings, config.allow_paper_simulation_approval)
    output_path = Path(config.output_path) if config.output_path else run_dir / "review.json"
    result = ReviewBoardResult(
        run_id=str(manifest.get("run_id", "")),
        strategy_id=str(manifest.get("strategy_id", "")),
        status=status,
        reviewed_at=datetime.now(UTC).isoformat(),
        findings=findings,
        metrics=metrics,
        diagnostics_summary=diagnostics_summary,
        manifest_path=str(manifest_path),
        backtest_path=str(backtest_path) if backtest_path is not None else None,
        diagnostics_path=str(diagnostics_path) if diagnostics_path is not None else None,
        output_path=str(output_path),
        safety_flags=safety_flags,
    )
    save_review_board_result(result, output_path)
    return result


def review_board_result_to_dict(result: ReviewBoardResult) -> dict[str, Any]:
    """Convert a review board result to a JSON-serializable dictionary."""
    return asdict(result)


def save_review_board_result(result: ReviewBoardResult, path: str | Path) -> Path:
    """Save a review board result as JSON."""
    return save_json_report(review_board_result_to_dict(result), path)


def _safety_flag_findings(safety_flags: dict[str, Any]) -> list[ReviewFinding]:
    findings = []
    for key, expected in _REQUIRED_SAFETY_FLAGS.items():
        actual = safety_flags.get(key)
        if actual is not expected:
            findings.append(
                ReviewFinding(
                    code="unsafe_manifest_safety_flag",
                    severity=REVIEW_CRITICAL,
                    message=f"Manifest safety flag {key} expected {expected}, found {actual}.",
                )
            )
    return findings


def _extract_metrics(
    backtest: dict[str, Any] | None,
    manifest: dict[str, Any],
    findings: list[ReviewFinding],
) -> dict[str, Any]:
    if isinstance(backtest, dict) and isinstance(backtest.get("metrics"), dict):
        return dict(backtest["metrics"])
    if isinstance(manifest.get("metrics_summary"), dict):
        findings.append(
            ReviewFinding(
                code="metrics_loaded_from_manifest",
                severity=REVIEW_WARNING,
                message="Backtest metrics were unavailable; using manifest metrics summary.",
            )
        )
        return dict(manifest["metrics_summary"])
    findings.append(
        ReviewFinding(
            code="missing_or_malformed_metrics",
            severity=REVIEW_WARNING,
            message="Backtest metrics are missing or malformed.",
        )
    )
    return {}


def _metric_findings(metrics: dict[str, Any], config: ReviewBoardConfig) -> list[ReviewFinding]:
    findings: list[ReviewFinding] = []
    trade_count = _as_int(metrics.get("trade_count"))
    if trade_count is None:
        findings.append(
            ReviewFinding(
                code="missing_trade_count",
                severity=REVIEW_WARNING,
                message="Metric trade_count is missing or malformed.",
            )
        )
    elif trade_count == 0:
        findings.append(
            ReviewFinding(
                code="zero_trades",
                severity=REVIEW_CRITICAL,
                message="Backtest produced zero trades.",
            )
        )
    elif trade_count < config.min_trades:
        findings.append(
            ReviewFinding(
                code="low_trade_count",
                severity=REVIEW_WARNING,
                message=f"trade_count {trade_count} is below minimum {config.min_trades}.",
            )
        )

    max_drawdown = _as_float(metrics.get("max_drawdown"))
    if max_drawdown is None:
        findings.append(
            ReviewFinding(
                code="missing_max_drawdown",
                severity=REVIEW_WARNING,
                message="Metric max_drawdown is missing or malformed.",
            )
        )
    elif max_drawdown < -abs(config.max_drawdown_pct):
        findings.append(
            ReviewFinding(
                code="max_drawdown_breach",
                severity=REVIEW_WARNING,
                message=(
                    f"max_drawdown {max_drawdown:.4f} is worse than "
                    f"-{abs(config.max_drawdown_pct):.4f}."
                ),
            )
        )
    return findings


def _extract_diagnostics_summary(diagnostics: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(diagnostics, dict):
        return {}
    summary = diagnostics.get("summary")
    if isinstance(summary, dict):
        result = dict(summary)
    else:
        result = {}
    result["ok"] = diagnostics.get("ok")
    issues = diagnostics.get("issues", [])
    result["issue_count"] = len(issues) if isinstance(issues, list) else 0
    return result


def _diagnostic_findings(
    diagnostics: dict[str, Any] | None,
    diagnostics_summary: dict[str, Any],
    config: ReviewBoardConfig,
) -> list[ReviewFinding]:
    if diagnostics is None:
        return []
    findings = []
    issues = diagnostics.get("issues", [])
    if not isinstance(issues, list):
        return [
            ReviewFinding(
                code="malformed_diagnostics",
                severity=REVIEW_WARNING,
                message="Diagnostics issues are malformed.",
            )
        ]

    for issue in issues:
        if not isinstance(issue, dict):
            continue
        code = str(issue.get("code", "diagnostic_issue"))
        if code in _DIAGNOSTIC_WARNING_CODES or issue.get("severity") in {"warning", "error"}:
            findings.append(
                ReviewFinding(
                    code=f"diagnostic_{code}",
                    severity=REVIEW_WARNING,
                    message=str(issue.get("message", "Diagnostic issue requires review.")),
                )
            )

    window_count = _as_int(diagnostics_summary.get("window_count"))
    if window_count is not None and window_count < config.min_walk_forward_windows:
        findings.append(
            ReviewFinding(
                code="insufficient_walk_forward_windows",
                severity=REVIEW_WARNING,
                message=(
                    f"walk-forward window_count {window_count} is below "
                    f"minimum {config.min_walk_forward_windows}."
                ),
            )
        )
    return findings


def _report_language_findings(report_path: Path | None) -> list[ReviewFinding]:
    if report_path is None or not report_path.exists():
        return []
    text = report_path.read_text(encoding="utf-8").lower()
    findings = []
    for phrase in _PROFIT_GUARANTEE_PHRASES:
        if phrase in text:
            findings.append(
                ReviewFinding(
                    code="profit_guarantee_language",
                    severity=REVIEW_WARNING,
                    message=f"Report contains disallowed profitability language: {phrase}.",
                )
            )
    return findings


def _cpcv_findings(
    cpcv_path: Path | None,
    config: ReviewBoardConfig,
) -> list[ReviewFinding]:
    """Check CPCV overfitting findings from research run."""
    if cpcv_path is None or not cpcv_path.exists():
        return []
    findings = []
    try:
        data = json.loads(cpcv_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    summary = data.get("summary", {})
    bop = summary.get("backtest_overfitting_probability")
    dsr = summary.get("deflated_sharpe_ratio")
    n_paths = summary.get("n_paths_tested", 0)
    disclaimer = data.get("disclaimer", "")

    if n_paths > 0:
        findings.append(
            ReviewFinding(
                code="cpcv_n_paths",
                severity=REVIEW_INFO,
                message=f"CPCV tested {n_paths} combinatorial paths.",
            )
        )
        findings.append(
            ReviewFinding(
                code="cpcv_mean_sharpe",
                severity=REVIEW_INFO,
                message=f"CPCV mean path Sharpe: {summary.get('mean_path_sharpe', 0):.3f}",
            )
        )

    if bop is not None and bop > config.cpcv_overfitting_threshold:
        findings.append(
            ReviewFinding(
                code="cpcv_overfitting_probability",
                severity=REVIEW_WARNING,
                message=(
                    f"CPCV indicates elevated overfitting risk: "
                    f"backtest_overfitting_probability={bop:.2%} > {config.cpcv_overfitting_threshold:.0%}. "
                    "CPCV indicates elevated overfitting risk. "
                    f"Deflated Sharpe Ratio={dsr:.3f}."
                ),
            )
        )
    elif bop is not None and n_paths > 0:
        findings.append(
            ReviewFinding(
                code="cpcv_overfitting_ok",
                severity=REVIEW_INFO,
                message=f"CPCV overfitting probability {bop:.2%} is within acceptable range.",
            )
        )

    if dsr is not None and 0 < dsr < config.cpcv_deflated_sharpe_threshold:
        findings.append(
            ReviewFinding(
                code="cpcv_deflated_sharpe_ratio_low",
                severity=REVIEW_WARNING,
                message=(
                    f"CPCV Deflated Sharpe Ratio={dsr:.3f} < {config.cpcv_deflated_sharpe_threshold:.1f}. "
                    "Strategy edge may not survive multiple testing correction."
                ),
            )
        )

    if disclaimer:
        findings.append(
            ReviewFinding(
                code="cpcv_disclaimer_present",
                severity=REVIEW_INFO,
                message="CPCV report includes mandatory disclaimer.",
            )
        )

    return findings


def _leakage_findings(leakage_path: Path | None) -> list[ReviewFinding]:
    """Check leakage detection findings from research run."""
    if leakage_path is None or not leakage_path.exists():
        return []
    findings = []
    try:
        data = json.loads(leakage_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    verdict = data.get("verdict", "UNKNOWN")
    critical_count = data.get("critical_count", 0)
    warning_count = data.get("warning_count", 0)

    if verdict == "COMPROMISED":
        findings.append(
            ReviewFinding(
                code="feature_leakage_detected",
                severity=REVIEW_CRITICAL,
                message=(
                    f"Feature leakage detected (COMPROMISED verdict). "
                    f"{critical_count} critical findings, {warning_count} warnings. "
                    "Results are invalid. Remove forward-looking features before "
                    "proceeding. "
                    "Feature leakage detected — results invalid."
                ),
            )
        )
    elif verdict == "SUSPECT":
        findings.append(
            ReviewFinding(
                code="feature_leakage_suspect",
                severity=REVIEW_WARNING,
                message=(
                    f"Feature leakage investigation recommended (SUSPECT verdict). "
                    f"{warning_count} warnings. Review leakage_report.json."
                ),
            )
        )
    elif verdict == "CLEAN":
        findings.append(
            ReviewFinding(
                code="feature_leakage_verified_clean",
                severity=REVIEW_INFO,
                message="Feature leakage detection passed (CLEAN verdict).",
            )
        )

    return findings


def _decide_status(
    findings: list[ReviewFinding],
    allow_paper_simulation_approval: bool,
) -> str:
    if any(finding.severity == REVIEW_CRITICAL for finding in findings):
        return REVIEW_REJECTED
    if any(finding.severity == REVIEW_WARNING for finding in findings):
        return REVIEW_NEEDS_MORE_RESEARCH
    if not allow_paper_simulation_approval:
        return REVIEW_NEEDS_MORE_RESEARCH
    return REVIEW_APPROVED_FOR_PAPER_SIMULATION


def _load_optional_json(
    path: Path | None,
    findings: list[ReviewFinding],
    missing_code: str,
    missing_severity: str,
) -> dict[str, Any] | None:
    if path is None or not path.exists():
        findings.append(
            ReviewFinding(
                code=missing_code,
                severity=missing_severity,
                message=f"Required artifact is missing: {path}.",
            )
        )
        return None
    return _load_json(path)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewBoardError(f"Could not read JSON artifact: {path}") from exc
    if not isinstance(data, dict):
        raise ReviewBoardError(f"JSON artifact must contain an object: {path}")
    return data


def _artifact_path(
    manifest: dict[str, Any],
    run_dir: Path,
    artifact_key: str,
    fallback_name: str,
) -> Path | None:
    artifacts = manifest.get("artifact_paths")
    if isinstance(artifacts, dict) and artifacts.get(artifact_key):
        return Path(str(artifacts[artifact_key]))
    fallback = run_dir / fallback_name
    return fallback if fallback.exists() else None


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
