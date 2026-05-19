"""Artifact-only review for local paper simulation outputs."""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from aurora.execution.exceptions import AuroraExecutionError
from aurora.reporting.reports import save_json_report
from aurora.risk.models import (
    RISK_APPROVED,
    RISK_KILL_SWITCH_TRIGGERED,
    RISK_REDUCED_SIZE,
    RISK_REJECTED,
)

PAPER_SIM_REVIEW_PASS = "PASS"
PAPER_SIM_REVIEW_WARN = "WARN"
PAPER_SIM_REVIEW_FAIL = "FAIL"

PAPER_SIM_REVIEW_INFO = "INFO"
PAPER_SIM_REVIEW_WARNING = "WARN"
PAPER_SIM_REVIEW_FAILURE = "FAIL"

ORDER_FILLED = "FILLED"
ORDER_REJECTED = "REJECTED"

REVIEW_SAFETY_FLAGS = {
    "paper_sim_review_only": True,
    "local_paper_simulation_only": True,
    "live_trading": False,
    "real_broker_used": False,
    "placed_real_orders": False,
    "external_llm_calls": False,
    "wrote_ledger": False,
}
REQUIRED_SIMULATION_SAFETY_FLAGS = {
    "local_paper_simulation_only": True,
    "live_trading": False,
    "real_broker_used": False,
    "placed_real_orders": False,
    "external_llm_calls": False,
}


@dataclass(frozen=True)
class PaperSimReviewFinding:
    """Single paper simulation review finding."""

    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class PaperSimReviewConfig:
    """Configuration for reviewing local paper simulation artifacts."""

    run_dir: str
    simulation_dir: str | None = None
    output_path: str | None = None
    require_simulation_manifest: bool = True
    require_risk_decisions: bool = True
    require_orders: bool = True
    fail_on_kill_switch: bool = True
    max_rejected_order_ratio: float = 0.50
    max_reduced_order_ratio: float = 0.50


@dataclass(frozen=True)
class PaperSimReviewResult:
    """Result from reviewing local paper simulation artifacts."""

    run_id: str
    strategy_id: str
    status: str
    reviewed_at: str
    findings: list[PaperSimReviewFinding]
    run_dir: str
    simulation_dir: str
    output_path: str
    simulation_manifest_path: str | None
    orders_path: str | None
    risk_decisions_path: str | None
    account_path: str | None
    positions_path: str | None
    summary: dict[str, Any]
    safety_flags: dict[str, Any]


class PaperSimReviewError(AuroraExecutionError):
    """Raised when a paper simulation review cannot be created."""


def review_paper_simulation(config: PaperSimReviewConfig) -> PaperSimReviewResult:
    """Review existing local paper simulation artifacts without executing anything."""
    _validate_config(config)
    run_dir = Path(config.run_dir)
    if not run_dir.exists() or not run_dir.is_dir():
        raise PaperSimReviewError(f"Research run directory not found: {run_dir}")

    simulation_dir = Path(config.simulation_dir) if config.simulation_dir else run_dir / "paper_simulation"
    output_path = Path(config.output_path) if config.output_path else simulation_dir / "paper_sim_review.json"
    reviewed_at = datetime.now(UTC).isoformat()

    simulation_manifest_path = simulation_dir / "simulation_manifest.json"
    orders_path = simulation_dir / "orders.jsonl"
    risk_decisions_path = simulation_dir / "risk_decisions.jsonl"
    account_path = simulation_dir / "account.json"
    positions_path = simulation_dir / "positions.json"

    findings: list[PaperSimReviewFinding] = []
    simulation_manifest = _load_simulation_manifest(
        simulation_manifest_path,
        config.require_simulation_manifest,
        findings,
    )
    prior_manifest = _load_optional_json(run_dir / "manifest.json", findings, "prior_manifest")
    orders = _load_jsonl_artifact(orders_path, config.require_orders, "orders", findings)
    risk_decisions = _load_jsonl_artifact(
        risk_decisions_path,
        config.require_risk_decisions,
        "risk_decisions",
        findings,
    )
    account = _load_optional_json(account_path, findings, "account")
    positions = _load_optional_json(positions_path, findings, "positions")

    if simulation_manifest is not None:
        findings.extend(_simulation_safety_findings(simulation_manifest.get("safety_flags")))

    summary = _summarize(
        orders=orders,
        risk_decisions=risk_decisions,
        account=account,
        positions=positions,
    )
    findings.extend(_relationship_findings(orders, risk_decisions))
    findings.extend(_kill_switch_findings(risk_decisions, config.fail_on_kill_switch))
    findings.extend(_ratio_findings(summary, config))
    findings.extend(_state_file_findings(account, positions))

    status = _status_from_findings(findings)
    result = PaperSimReviewResult(
        run_id=_run_id(simulation_manifest, prior_manifest, run_dir),
        strategy_id=_strategy_id(simulation_manifest, prior_manifest),
        status=status,
        reviewed_at=reviewed_at,
        findings=findings,
        run_dir=str(run_dir),
        simulation_dir=str(simulation_dir),
        output_path=str(output_path),
        simulation_manifest_path=str(simulation_manifest_path) if simulation_manifest_path.exists() else None,
        orders_path=str(orders_path) if orders_path.exists() else None,
        risk_decisions_path=str(risk_decisions_path) if risk_decisions_path.exists() else None,
        account_path=str(account_path) if account_path.exists() else None,
        positions_path=str(positions_path) if positions_path.exists() else None,
        summary=summary,
        safety_flags=dict(REVIEW_SAFETY_FLAGS),
    )
    save_paper_sim_review_result(result, output_path)
    return result


def paper_sim_review_result_to_dict(result: PaperSimReviewResult) -> dict[str, Any]:
    """Convert a paper simulation review result to a JSON-serializable dictionary."""
    return asdict(result)


def save_paper_sim_review_result(
    result: PaperSimReviewResult,
    path: str | Path,
) -> Path:
    """Save the paper simulation review artifact."""
    return save_json_report(paper_sim_review_result_to_dict(result), path)


def _validate_config(config: PaperSimReviewConfig) -> None:
    if not 0 <= config.max_rejected_order_ratio <= 1:
        raise PaperSimReviewError("max_rejected_order_ratio must be between 0 and 1.")
    if not 0 <= config.max_reduced_order_ratio <= 1:
        raise PaperSimReviewError("max_reduced_order_ratio must be between 0 and 1.")


def _load_simulation_manifest(
    path: Path,
    required: bool,
    findings: list[PaperSimReviewFinding],
) -> dict[str, Any] | None:
    if not path.exists():
        findings.append(
            PaperSimReviewFinding(
                code="missing_simulation_manifest",
                severity=PAPER_SIM_REVIEW_FAILURE if required else PAPER_SIM_REVIEW_WARNING,
                message=f"Simulation manifest is missing: {path}.",
            )
        )
        return None
    return _load_json_artifact(path, findings, "simulation_manifest")


def _load_optional_json(
    path: Path,
    findings: list[PaperSimReviewFinding],
    artifact_name: str,
) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return _load_json_artifact(path, findings, artifact_name)


def _load_json_artifact(
    path: Path,
    findings: list[PaperSimReviewFinding],
    artifact_name: str,
) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        findings.append(
            PaperSimReviewFinding(
                code=f"malformed_{artifact_name}",
                severity=PAPER_SIM_REVIEW_FAILURE,
                message=f"Could not parse {artifact_name} JSON at {path}: {exc}.",
            )
        )
        return None
    if not isinstance(data, dict):
        findings.append(
            PaperSimReviewFinding(
                code=f"malformed_{artifact_name}",
                severity=PAPER_SIM_REVIEW_FAILURE,
                message=f"{artifact_name} must contain a JSON object: {path}.",
            )
        )
        return None
    return data


def _load_jsonl_artifact(
    path: Path,
    required: bool,
    artifact_name: str,
    findings: list[PaperSimReviewFinding],
) -> list[dict[str, Any]]:
    if not path.exists():
        if required:
            findings.append(
                PaperSimReviewFinding(
                    code=f"missing_{artifact_name}",
                    severity=PAPER_SIM_REVIEW_FAILURE,
                    message=f"Required {artifact_name} artifact is missing: {path}.",
                )
            )
        return []

    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            findings.append(
                PaperSimReviewFinding(
                    code=f"malformed_{artifact_name}_line",
                    severity=PAPER_SIM_REVIEW_WARNING,
                    message=f"Skipped malformed {artifact_name} line {line_number}: {exc}.",
                )
            )
            continue
        if isinstance(value, dict):
            rows.append(value)
        else:
            findings.append(
                PaperSimReviewFinding(
                    code=f"malformed_{artifact_name}_line",
                    severity=PAPER_SIM_REVIEW_WARNING,
                    message=f"Skipped non-object {artifact_name} line {line_number}.",
                )
            )
    return rows


def _simulation_safety_findings(safety_flags: object) -> list[PaperSimReviewFinding]:
    if not isinstance(safety_flags, dict):
        return [
            PaperSimReviewFinding(
                code="missing_simulation_safety_flags",
                severity=PAPER_SIM_REVIEW_FAILURE,
                message="Simulation manifest safety flags are missing or malformed.",
            )
        ]

    findings = []
    for key, expected in REQUIRED_SIMULATION_SAFETY_FLAGS.items():
        actual = safety_flags.get(key)
        if actual is not expected:
            findings.append(
                PaperSimReviewFinding(
                    code="unsafe_simulation_safety_flag",
                    severity=PAPER_SIM_REVIEW_FAILURE,
                    message=f"Simulation safety flag {key} expected {expected}, found {actual}.",
                )
            )
    return findings


def _summarize(
    orders: list[dict[str, Any]],
    risk_decisions: list[dict[str, Any]],
    account: dict[str, Any] | None,
    positions: dict[str, Any] | None,
) -> dict[str, Any]:
    total_orders = len(orders)
    rejected_orders = _count_values(orders, "status", ORDER_REJECTED)
    reduced_orders = _count_values(orders, "risk_status", RISK_REDUCED_SIZE)
    total_risk_decisions = len(risk_decisions)
    return {
        "total_orders": total_orders,
        "filled_orders": _count_values(orders, "status", ORDER_FILLED),
        "rejected_orders": rejected_orders,
        "reduced_orders": reduced_orders,
        "rejected_order_ratio": rejected_orders / total_orders if total_orders else 0.0,
        "reduced_order_ratio": reduced_orders / total_orders if total_orders else 0.0,
        "total_risk_decisions": total_risk_decisions,
        "approved_decisions": _count_values(risk_decisions, "status", RISK_APPROVED),
        "rejected_decisions": _count_values(risk_decisions, "status", RISK_REJECTED),
        "reduced_size_decisions": _count_values(risk_decisions, "status", RISK_REDUCED_SIZE),
        "kill_switch_decisions": _count_values(
            risk_decisions,
            "status",
            RISK_KILL_SWITCH_TRIGGERED,
        ),
        "open_positions": len(positions or {}),
        "final_cash": account.get("cash") if isinstance(account, dict) else None,
        "final_equity": account.get("equity") if isinstance(account, dict) else None,
    }


def _relationship_findings(
    orders: list[dict[str, Any]],
    risk_decisions: list[dict[str, Any]],
) -> list[PaperSimReviewFinding]:
    if orders and not risk_decisions:
        return [
            PaperSimReviewFinding(
                code="orders_without_risk_decisions",
                severity=PAPER_SIM_REVIEW_FAILURE,
                message="Orders exist but no risk decisions were found.",
            )
        ]
    if risk_decisions and not orders:
        return [
            PaperSimReviewFinding(
                code="risk_decisions_without_orders",
                severity=PAPER_SIM_REVIEW_WARNING,
                message="Risk decisions exist but no orders were found.",
            )
        ]
    return []


def _kill_switch_findings(
    risk_decisions: list[dict[str, Any]],
    fail_on_kill_switch: bool,
) -> list[PaperSimReviewFinding]:
    count = _count_values(risk_decisions, "status", RISK_KILL_SWITCH_TRIGGERED)
    if count == 0:
        return []
    return [
        PaperSimReviewFinding(
            code="kill_switch_decision",
            severity=PAPER_SIM_REVIEW_FAILURE if fail_on_kill_switch else PAPER_SIM_REVIEW_WARNING,
            message=f"Found {count} kill-switch risk decision(s).",
        )
    ]


def _ratio_findings(
    summary: dict[str, Any],
    config: PaperSimReviewConfig,
) -> list[PaperSimReviewFinding]:
    findings = []
    rejected_ratio = float(summary.get("rejected_order_ratio", 0.0) or 0.0)
    if rejected_ratio > config.max_rejected_order_ratio:
        findings.append(
            PaperSimReviewFinding(
                code="high_rejected_order_ratio",
                severity=PAPER_SIM_REVIEW_WARNING,
                message=(
                    f"Rejected order ratio {rejected_ratio:.2f} exceeds "
                    f"{config.max_rejected_order_ratio:.2f}."
                ),
            )
        )
    reduced_ratio = float(summary.get("reduced_order_ratio", 0.0) or 0.0)
    if reduced_ratio > config.max_reduced_order_ratio:
        findings.append(
            PaperSimReviewFinding(
                code="high_reduced_order_ratio",
                severity=PAPER_SIM_REVIEW_WARNING,
                message=(
                    f"Reduced order ratio {reduced_ratio:.2f} exceeds "
                    f"{config.max_reduced_order_ratio:.2f}."
                ),
            )
        )
    return findings


def _state_file_findings(
    account: dict[str, Any] | None,
    positions: dict[str, Any] | None,
) -> list[PaperSimReviewFinding]:
    findings = []
    if account is None:
        findings.append(
            PaperSimReviewFinding(
                code="missing_account",
                severity=PAPER_SIM_REVIEW_WARNING,
                message="Account artifact is missing or unreadable.",
            )
        )
    if positions is None:
        findings.append(
            PaperSimReviewFinding(
                code="missing_positions",
                severity=PAPER_SIM_REVIEW_WARNING,
                message="Positions artifact is missing or unreadable.",
            )
        )
    return findings


def _status_from_findings(findings: list[PaperSimReviewFinding]) -> str:
    if any(finding.severity == PAPER_SIM_REVIEW_FAILURE for finding in findings):
        return PAPER_SIM_REVIEW_FAIL
    if any(finding.severity == PAPER_SIM_REVIEW_WARNING for finding in findings):
        return PAPER_SIM_REVIEW_WARN
    return PAPER_SIM_REVIEW_PASS


def _count_values(items: list[dict[str, Any]], key: str, expected: str) -> int:
    return sum(1 for item in items if item.get(key) == expected)


def _run_id(
    simulation_manifest: dict[str, Any] | None,
    prior_manifest: dict[str, Any] | None,
    run_dir: Path,
) -> str:
    if isinstance(simulation_manifest, dict) and simulation_manifest.get("run_id"):
        return str(simulation_manifest["run_id"])
    if isinstance(prior_manifest, dict) and prior_manifest.get("run_id"):
        return str(prior_manifest["run_id"])
    return run_dir.name


def _strategy_id(
    simulation_manifest: dict[str, Any] | None,
    prior_manifest: dict[str, Any] | None,
) -> str:
    if isinstance(simulation_manifest, dict) and simulation_manifest.get("strategy_id"):
        return str(simulation_manifest["strategy_id"])
    if isinstance(prior_manifest, dict) and prior_manifest.get("strategy_id"):
        return str(prior_manifest["strategy_id"])
    return "unknown"
