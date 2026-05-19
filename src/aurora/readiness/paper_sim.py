"""Artifact-only gate for future local paper simulation readiness."""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from aurora.reporting.reports import save_json_report
from aurora.review.board import (
    REVIEW_APPROVED_FOR_PAPER_SIMULATION,
    REVIEW_CRITICAL,
    REVIEW_NEEDS_MORE_RESEARCH,
    REVIEW_REJECTED,
)

PAPER_SIM_BLOCKED = "BLOCKED"
PAPER_SIM_READY = "READY_FOR_PAPER_SIMULATION"
PAPER_SIM_NEEDS_MORE_RESEARCH = "NEEDS_MORE_RESEARCH"

READINESS_INFO = "INFO"
READINESS_WARNING = "WARNING"
READINESS_CRITICAL = "CRITICAL"

_REQUIRED_SAFETY_FLAGS = {
    "research_only": True,
    "placed_orders": False,
    "used_broker": False,
    "wrote_ledger": False,
    "external_llm_calls": False,
}
_REVIEW_STATUS_RANK = {
    REVIEW_REJECTED: 0,
    REVIEW_NEEDS_MORE_RESEARCH: 1,
    REVIEW_APPROVED_FOR_PAPER_SIMULATION: 2,
}
_LEDGER_FILENAMES = [
    "orders.jsonl",
    "risk_decisions.jsonl",
    "account.json",
    "positions.json",
]


@dataclass(frozen=True)
class PaperSimReadinessFinding:
    """Single deterministic paper simulation readiness finding."""

    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class PaperSimReadinessConfig:
    """Configuration for evaluating future paper simulation readiness."""

    run_dir: str
    output_path: str | None = None
    require_review_approval: bool = True
    require_research_only_manifest: bool = True
    require_no_critical_review_findings: bool = True
    require_no_ledger_writes: bool = True
    min_trades: int = 50
    max_drawdown_pct: float = 0.25
    min_required_status: str = REVIEW_APPROVED_FOR_PAPER_SIMULATION


@dataclass(frozen=True)
class PaperSimReadinessResult:
    """Result from the local paper simulation readiness gate."""

    run_id: str
    strategy_id: str
    status: str
    evaluated_at: str
    findings: list[PaperSimReadinessFinding]
    manifest_path: str
    review_path: str
    backtest_path: str | None
    diagnostics_path: str | None
    output_path: str
    safety_flags: dict[str, Any]
    review_status: str | None
    metrics: dict[str, Any]


class PaperSimReadinessError(Exception):
    """Raised when readiness cannot be evaluated."""


def evaluate_paper_sim_readiness(
    config: PaperSimReadinessConfig,
) -> PaperSimReadinessResult:
    """Evaluate whether artifacts are eligible for future local paper simulation."""
    _validate_config(config)
    run_dir = Path(config.run_dir)
    manifest_path = run_dir / "manifest.json"
    review_path = run_dir / "review.json"
    if not manifest_path.exists():
        raise PaperSimReadinessError(f"Research run manifest not found: {manifest_path}")
    if not review_path.exists():
        raise PaperSimReadinessError(f"Review artifact not found: {review_path}")

    manifest = _load_json(manifest_path)
    review = _load_json(review_path)
    findings: list[PaperSimReadinessFinding] = []
    safety_flags = _safe_dict(manifest.get("safety_flags"))
    if config.require_research_only_manifest:
        findings.extend(_safety_flag_findings(safety_flags))

    review_status = _safe_str(review.get("status"))
    findings.extend(_review_status_findings(review_status, config))
    findings.extend(_critical_review_finding_findings(review, config))

    backtest_path = _artifact_path(manifest, run_dir, "backtest", "backtest.json")
    backtest = _load_optional_json(backtest_path)
    metrics = _extract_metrics(backtest, manifest, review)
    findings.extend(_metric_findings(metrics, config))

    diagnostics_path = _artifact_path(manifest, run_dir, "diagnostics", "diagnostics.json")
    _load_optional_json(diagnostics_path)

    if config.require_no_ledger_writes:
        findings.extend(_ledger_findings(run_dir))

    status = _decide_status(findings)
    output_path = (
        Path(config.output_path)
        if config.output_path
        else run_dir / "paper_sim_readiness.json"
    )
    result = PaperSimReadinessResult(
        run_id=str(manifest.get("run_id", "")),
        strategy_id=str(manifest.get("strategy_id", "")),
        status=status,
        evaluated_at=datetime.now(UTC).isoformat(),
        findings=findings,
        manifest_path=str(manifest_path),
        review_path=str(review_path),
        backtest_path=str(backtest_path) if backtest_path is not None else None,
        diagnostics_path=str(diagnostics_path) if diagnostics_path is not None else None,
        output_path=str(output_path),
        safety_flags=safety_flags,
        review_status=review_status,
        metrics=metrics,
    )
    save_paper_sim_readiness_result(result, output_path)
    return result


def paper_sim_readiness_result_to_dict(
    result: PaperSimReadinessResult,
) -> dict[str, Any]:
    """Convert a readiness result to a JSON-serializable dictionary."""
    return asdict(result)


def save_paper_sim_readiness_result(
    result: PaperSimReadinessResult,
    path: str | Path,
) -> Path:
    """Save a readiness result as JSON."""
    return save_json_report(paper_sim_readiness_result_to_dict(result), path)


def _validate_config(config: PaperSimReadinessConfig) -> None:
    if config.min_trades < 0:
        raise PaperSimReadinessError("min_trades must be non-negative.")
    if config.max_drawdown_pct < 0:
        raise PaperSimReadinessError("max_drawdown_pct must be non-negative.")
    if config.min_required_status not in _REVIEW_STATUS_RANK:
        raise PaperSimReadinessError(
            f"Unsupported min_required_status: {config.min_required_status}"
        )


def _safety_flag_findings(safety_flags: dict[str, Any]) -> list[PaperSimReadinessFinding]:
    findings = []
    for key, expected in _REQUIRED_SAFETY_FLAGS.items():
        actual = safety_flags.get(key)
        if actual is not expected:
            findings.append(
                PaperSimReadinessFinding(
                    code="unsafe_manifest_safety_flag",
                    severity=READINESS_CRITICAL,
                    message=f"Manifest safety flag {key} expected {expected}, found {actual}.",
                )
            )
    return findings


def _review_status_findings(
    review_status: str | None,
    config: PaperSimReadinessConfig,
) -> list[PaperSimReadinessFinding]:
    if review_status == REVIEW_REJECTED:
        return [
            PaperSimReadinessFinding(
                code="review_rejected",
                severity=READINESS_CRITICAL,
                message="Review Board status is REJECTED.",
            )
        ]

    if review_status not in _REVIEW_STATUS_RANK:
        return [
            PaperSimReadinessFinding(
                code="missing_or_unknown_review_status",
                severity=READINESS_CRITICAL,
                message=f"Review status is missing or unsupported: {review_status}.",
            )
        ]

    if config.require_review_approval:
        required_rank = _REVIEW_STATUS_RANK[config.min_required_status]
        actual_rank = _REVIEW_STATUS_RANK[review_status]
        if actual_rank < required_rank:
            return [
                PaperSimReadinessFinding(
                    code="review_status_below_required",
                    severity=READINESS_CRITICAL,
                    message=(
                        f"Review status {review_status} is below required "
                        f"{config.min_required_status}."
                    ),
                )
            ]

    if not config.require_review_approval and review_status == REVIEW_NEEDS_MORE_RESEARCH:
        return [
            PaperSimReadinessFinding(
                code="review_needs_more_research",
                severity=READINESS_WARNING,
                message="Review Board status indicates more research is needed.",
            )
        ]
    return []


def _critical_review_finding_findings(
    review: dict[str, Any],
    config: PaperSimReadinessConfig,
) -> list[PaperSimReadinessFinding]:
    if not config.require_no_critical_review_findings:
        return []
    findings = review.get("findings", [])
    if not isinstance(findings, list):
        return [
            PaperSimReadinessFinding(
                code="malformed_review_findings",
                severity=READINESS_CRITICAL,
                message="Review findings are malformed.",
            )
        ]
    critical_codes = [
        str(finding.get("code", "review_finding"))
        for finding in findings
        if isinstance(finding, dict) and finding.get("severity") == REVIEW_CRITICAL
    ]
    return [
        PaperSimReadinessFinding(
            code="critical_review_finding",
            severity=READINESS_CRITICAL,
            message=f"Review contains critical finding: {code}.",
        )
        for code in critical_codes
    ]


def _extract_metrics(
    backtest: dict[str, Any] | None,
    manifest: dict[str, Any],
    review: dict[str, Any],
) -> dict[str, Any]:
    if isinstance(backtest, dict) and isinstance(backtest.get("metrics"), dict):
        return dict(backtest["metrics"])
    if isinstance(manifest.get("metrics_summary"), dict):
        return dict(manifest["metrics_summary"])
    if isinstance(review.get("metrics"), dict):
        return dict(review["metrics"])
    return {}


def _metric_findings(
    metrics: dict[str, Any],
    config: PaperSimReadinessConfig,
) -> list[PaperSimReadinessFinding]:
    findings = []
    trade_count = _as_int(metrics.get("trade_count"))
    if trade_count is None:
        findings.append(
            PaperSimReadinessFinding(
                code="missing_trade_count",
                severity=READINESS_WARNING,
                message="Metric trade_count is missing or malformed.",
            )
        )
    elif trade_count == 0:
        findings.append(
            PaperSimReadinessFinding(
                code="zero_trades",
                severity=READINESS_CRITICAL,
                message="Backtest produced zero trades.",
            )
        )
    elif trade_count < config.min_trades:
        findings.append(
            PaperSimReadinessFinding(
                code="low_trade_count",
                severity=READINESS_WARNING,
                message=f"trade_count {trade_count} is below minimum {config.min_trades}.",
            )
        )

    max_drawdown = _as_float(metrics.get("max_drawdown"))
    if max_drawdown is None:
        findings.append(
            PaperSimReadinessFinding(
                code="missing_max_drawdown",
                severity=READINESS_WARNING,
                message="Metric max_drawdown is missing or malformed.",
            )
        )
    elif max_drawdown < -abs(config.max_drawdown_pct):
        findings.append(
            PaperSimReadinessFinding(
                code="max_drawdown_breach",
                severity=READINESS_WARNING,
                message=(
                    f"max_drawdown {max_drawdown:.4f} is worse than "
                    f"-{abs(config.max_drawdown_pct):.4f}."
                ),
            )
        )
    return findings


def _ledger_findings(run_dir: Path) -> list[PaperSimReadinessFinding]:
    findings = []
    for ledger_dir in _ledger_dirs_to_check(run_dir):
        if ledger_dir.exists():
            findings.append(
                PaperSimReadinessFinding(
                    code="ledger_directory_detected",
                    severity=READINESS_CRITICAL,
                    message=f"Ledger directory detected near research run: {ledger_dir}.",
                )
            )
        for filename in _LEDGER_FILENAMES:
            ledger_file = ledger_dir / filename
            if ledger_file.exists():
                findings.append(
                    PaperSimReadinessFinding(
                        code="ledger_artifact_detected",
                        severity=READINESS_CRITICAL,
                        message=f"Ledger artifact detected: {ledger_file}.",
                    )
                )
    return findings


def _ledger_dirs_to_check(run_dir: Path) -> list[Path]:
    candidates = [run_dir / "ledger", run_dir.parent / "ledger"]
    if run_dir.parent.name == "research_runs" and run_dir.parent.parent.name == "data":
        candidates.append(run_dir.parent.parent / "ledger")
    deduped = []
    for candidate in candidates:
        if candidate not in deduped:
            deduped.append(candidate)
    return deduped


def _decide_status(findings: list[PaperSimReadinessFinding]) -> str:
    if any(finding.severity == READINESS_CRITICAL for finding in findings):
        return PAPER_SIM_BLOCKED
    if any(finding.severity == READINESS_WARNING for finding in findings):
        return PAPER_SIM_NEEDS_MORE_RESEARCH
    return PAPER_SIM_READY


def _load_optional_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    return _load_json(path)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PaperSimReadinessError(f"Could not read JSON artifact: {path}") from exc
    if not isinstance(data, dict):
        raise PaperSimReadinessError(f"JSON artifact must contain an object: {path}")
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


def _safe_str(value: Any) -> str | None:
    return str(value) if value is not None else None


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
