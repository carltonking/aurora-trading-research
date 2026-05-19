"""Artifact-only paper simulation planning."""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from aurora.readiness.paper_sim import PAPER_SIM_READY
from aurora.reporting.reports import save_json_report

PAPER_SIM_PLAN_BLOCKED = "BLOCKED"
PAPER_SIM_PLAN_READY = "PLAN_READY"

PLAN_INFO = "INFO"
PLAN_WARNING = "WARNING"
PLAN_CRITICAL = "CRITICAL"

_REQUIRED_SAFETY_FLAGS = {
    "research_only": True,
    "placed_orders": False,
    "used_broker": False,
    "wrote_ledger": False,
    "external_llm_calls": False,
}
_PROHIBITED_ACTIONS = [
    "live_trading",
    "broker_order_placement",
    "direct_prompt_order_placement",
    "external_llm_calls",
]
_SAFETY_STATEMENT = "This is a non-executing plan for future local paper simulation only."


@dataclass(frozen=True)
class PaperSimPlanFinding:
    """Single deterministic paper simulation plan finding."""

    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class PaperSimPlanConfig:
    """Configuration for creating a future paper simulation plan."""

    run_dir: str
    output_path: str | None = None
    require_ready_status: bool = True
    default_initial_cash: float = 100000.0
    default_max_position_pct: float = 0.05
    default_slippage_bps: float = 5.0
    default_commission_bps: float = 1.0
    require_signals_artifact: bool = True
    require_risk_gate: bool = True


@dataclass(frozen=True)
class PaperSimPlanResult:
    """Result from the local paper simulation plan builder."""

    run_id: str
    strategy_id: str
    status: str
    planned_at: str
    findings: list[PaperSimPlanFinding]
    manifest_path: str
    review_path: str
    readiness_path: str
    signals_path: str | None
    output_path: str
    readiness_status: str | None
    safety_flags: dict[str, Any]
    plan: dict[str, Any]


class PaperSimPlanError(Exception):
    """Raised when a paper simulation plan cannot be created."""


def create_paper_sim_plan(config: PaperSimPlanConfig) -> PaperSimPlanResult:
    """Create a non-executing paper simulation plan from existing artifacts."""
    _validate_config(config)
    run_dir = Path(config.run_dir)
    manifest_path = run_dir / "manifest.json"
    review_path = run_dir / "review.json"
    readiness_path = run_dir / "paper_sim_readiness.json"
    if not manifest_path.exists():
        raise PaperSimPlanError(f"Research run manifest not found: {manifest_path}")
    if not review_path.exists():
        raise PaperSimPlanError(f"Review artifact not found: {review_path}")
    if not readiness_path.exists():
        raise PaperSimPlanError(f"Readiness artifact not found: {readiness_path}")

    manifest = _load_json(manifest_path)
    review = _load_json(review_path)
    readiness = _load_json(readiness_path)
    findings: list[PaperSimPlanFinding] = []

    safety_flags = _safe_dict(manifest.get("safety_flags"))
    findings.extend(_safety_flag_findings(safety_flags))

    readiness_status = _safe_str(readiness.get("status"))
    if config.require_ready_status and readiness_status != PAPER_SIM_READY:
        findings.append(
            PaperSimPlanFinding(
                code="readiness_not_ready",
                severity=PLAN_CRITICAL,
                message=f"Readiness status is {readiness_status}; expected {PAPER_SIM_READY}.",
            )
        )

    signals_path = _artifact_path(manifest, run_dir, "signals", "signals.csv")
    if config.require_signals_artifact and (signals_path is None or not signals_path.exists()):
        findings.append(
            PaperSimPlanFinding(
                code="missing_signals_artifact",
                severity=PLAN_CRITICAL,
                message=f"Signals artifact is required but missing: {signals_path}.",
            )
        )

    output_path = (
        Path(config.output_path)
        if config.output_path
        else run_dir / "paper_sim_plan.json"
    )
    plan = _build_plan(
        config=config,
        manifest=manifest,
        review=review,
        readiness=readiness,
        manifest_path=manifest_path,
        review_path=review_path,
        readiness_path=readiness_path,
        signals_path=signals_path,
    )
    status = _decide_status(findings)
    result = PaperSimPlanResult(
        run_id=str(manifest.get("run_id", "")),
        strategy_id=str(manifest.get("strategy_id", "")),
        status=status,
        planned_at=datetime.now(UTC).isoformat(),
        findings=findings,
        manifest_path=str(manifest_path),
        review_path=str(review_path),
        readiness_path=str(readiness_path),
        signals_path=str(signals_path) if signals_path is not None else None,
        output_path=str(output_path),
        readiness_status=readiness_status,
        safety_flags=safety_flags,
        plan=plan,
    )
    save_paper_sim_plan_result(result, output_path)
    return result


def paper_sim_plan_result_to_dict(result: PaperSimPlanResult) -> dict[str, Any]:
    """Convert a paper simulation plan result to a JSON-serializable dictionary."""
    return asdict(result)


def save_paper_sim_plan_result(result: PaperSimPlanResult, path: str | Path) -> Path:
    """Save a paper simulation plan result as JSON."""
    return save_json_report(paper_sim_plan_result_to_dict(result), path)


def _build_plan(
    config: PaperSimPlanConfig,
    manifest: dict[str, Any],
    review: dict[str, Any],
    readiness: dict[str, Any],
    manifest_path: Path,
    review_path: Path,
    readiness_path: Path,
    signals_path: Path | None,
) -> dict[str, Any]:
    backtest_path = _artifact_path(manifest, manifest_path.parent, "backtest", "backtest.json")
    diagnostics_path = _artifact_path(
        manifest,
        manifest_path.parent,
        "diagnostics",
        "diagnostics.json",
    )
    proposed_artifacts = {
        "signals_path": str(signals_path) if signals_path is not None else None,
        "manifest_path": str(manifest_path),
        "review_path": str(review_path),
        "readiness_path": str(readiness_path),
    }
    if backtest_path is not None:
        proposed_artifacts["backtest_path"] = str(backtest_path)
    if diagnostics_path is not None:
        proposed_artifacts["diagnostics_path"] = str(diagnostics_path)

    return {
        "run_id": str(manifest.get("run_id", "")),
        "strategy_id": str(manifest.get("strategy_id", "")),
        "symbols": list(manifest.get("symbols", []))
        if isinstance(manifest.get("symbols"), list)
        else [],
        "readiness_status": _safe_str(readiness.get("status")),
        "review_status": _safe_str(review.get("status")),
        "initial_cash": config.default_initial_cash,
        "max_position_pct": config.default_max_position_pct,
        "slippage_bps": config.default_slippage_bps,
        "commission_bps": config.default_commission_bps,
        "require_risk_gate": config.require_risk_gate,
        "proposed_input_artifacts": proposed_artifacts,
        "prohibited_actions": list(_PROHIBITED_ACTIONS),
        "safety_statement": _SAFETY_STATEMENT,
    }


def _safety_flag_findings(safety_flags: dict[str, Any]) -> list[PaperSimPlanFinding]:
    findings = []
    for key, expected in _REQUIRED_SAFETY_FLAGS.items():
        actual = safety_flags.get(key)
        if actual is not expected:
            findings.append(
                PaperSimPlanFinding(
                    code="unsafe_manifest_safety_flag",
                    severity=PLAN_CRITICAL,
                    message=f"Manifest safety flag {key} expected {expected}, found {actual}.",
                )
            )
    return findings


def _decide_status(findings: list[PaperSimPlanFinding]) -> str:
    if any(finding.severity == PLAN_CRITICAL for finding in findings):
        return PAPER_SIM_PLAN_BLOCKED
    return PAPER_SIM_PLAN_READY


def _validate_config(config: PaperSimPlanConfig) -> None:
    if config.default_initial_cash <= 0:
        raise PaperSimPlanError("default_initial_cash must be greater than 0.")
    if config.default_max_position_pct <= 0:
        raise PaperSimPlanError("default_max_position_pct must be greater than 0.")
    if config.default_slippage_bps < 0:
        raise PaperSimPlanError("default_slippage_bps must be non-negative.")
    if config.default_commission_bps < 0:
        raise PaperSimPlanError("default_commission_bps must be non-negative.")


def _artifact_path(
    manifest: dict[str, Any],
    run_dir: Path,
    artifact_key: str,
    fallback_name: str,
) -> Path | None:
    artifacts = manifest.get("artifact_paths")
    if isinstance(artifacts, dict) and artifacts.get(artifact_key):
        path = Path(str(artifacts[artifact_key]))
        return path if path.exists() else None
    fallback = run_dir / fallback_name
    return fallback if fallback.exists() else None


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PaperSimPlanError(f"Could not read JSON artifact: {path}") from exc
    if not isinstance(data, dict):
        raise PaperSimPlanError(f"JSON artifact must contain an object: {path}")
    return data


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str | None:
    return str(value) if value is not None else None
