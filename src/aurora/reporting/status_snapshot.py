"""Project status snapshot reporting."""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from aurora.reporting.reports import save_json_report

PROJECT_STATUS_FILENAME = "project_status.json"
PROJECT_STATUS_MARKDOWN_FILENAME = "project_status.md"

STATUS_SNAPSHOT_SAFETY_FLAGS = {
    "status_snapshot_only": True,
    "placed_orders": False,
    "used_broker": False,
    "wrote_ledger": False,
    "external_llm_calls": False,
}

CAPABILITIES = [
    "market data",
    "feature engineering",
    "model training and registry",
    "strategy registry and signal generation",
    "research-only backtesting",
    "validation and diagnostics",
    "risk manager hard gate",
    "local simulation broker and paper ledger",
    "reporting dashboard MVP",
    "deterministic Strategy Prompt Lab",
    "local research run orchestration with manifest safety flags",
    "Strategy Candidate Review Board with review.json",
    "Paper Simulation Readiness Gate with paper_sim_readiness.json",
    "Paper Simulation Plan with paper_sim_plan.json",
    "Research Artifact Packet Builder with artifact_packet/packet_manifest.json",
]

SAFETY_BOUNDARIES = [
    "research-first",
    "paper-trading-first",
    "no live trading",
    "no real broker execution",
    "no real order placement",
    "no direct order placement from prompts",
    "no external LLM/API calls",
    "no profitability claims",
]


@dataclass(frozen=True)
class ProjectStatusSnapshotConfig:
    """Configuration for a local project status snapshot."""

    output_dir: str = "data/status"
    include_recent_research_runs: bool = True
    research_runs_dir: str = "data/research_runs"
    max_recent_runs: int = 5
    latest_test_count: int | None = None


@dataclass(frozen=True)
class ProjectStatusSnapshotResult:
    """Result from creating a local project status snapshot."""

    created_at: str
    output_dir: str
    json_path: str
    markdown_path: str
    capabilities: list[str]
    safety_boundaries: list[str]
    artifact_locations: dict[str, str]
    recent_research_runs: list[dict[str, Any]]
    latest_test_count: int | None


def create_project_status_snapshot(
    config: ProjectStatusSnapshotConfig,
) -> ProjectStatusSnapshotResult:
    """Create JSON and Markdown summaries of local AURORA project status."""
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now(UTC).isoformat()
    artifact_locations = {
        "models": "data/models",
        "strategies": "data/strategies",
        "ledger": "data/ledger",
        "research_runs": config.research_runs_dir,
        "status": str(output_dir),
    }
    recent_runs = (
        _discover_recent_research_runs(Path(config.research_runs_dir), config.max_recent_runs)
        if config.include_recent_research_runs
        else []
    )

    result = ProjectStatusSnapshotResult(
        created_at=created_at,
        output_dir=str(output_dir),
        json_path=str(output_dir / PROJECT_STATUS_FILENAME),
        markdown_path=str(output_dir / PROJECT_STATUS_MARKDOWN_FILENAME),
        capabilities=list(CAPABILITIES),
        safety_boundaries=list(SAFETY_BOUNDARIES),
        artifact_locations=artifact_locations,
        recent_research_runs=recent_runs,
        latest_test_count=config.latest_test_count,
    )
    save_project_status_snapshot_json(result, result.json_path)
    Path(result.markdown_path).write_text(render_project_status_markdown(result), encoding="utf-8")
    return result


def project_status_snapshot_result_to_dict(
    result: ProjectStatusSnapshotResult,
) -> dict[str, Any]:
    """Convert a project status snapshot to a JSON-serializable dictionary."""
    payload = asdict(result)
    payload["safety_flags"] = dict(STATUS_SNAPSHOT_SAFETY_FLAGS)
    return payload


def save_project_status_snapshot_json(
    result: ProjectStatusSnapshotResult,
    path: str | Path,
) -> None:
    """Save a project status snapshot JSON artifact."""
    save_json_report(project_status_snapshot_result_to_dict(result), path)


def render_project_status_markdown(result: ProjectStatusSnapshotResult) -> str:
    """Render a project status snapshot as Markdown."""
    lines = [
        "# AURORA Trading Research Project Status",
        "",
        f"Created: {result.created_at}",
        "",
        (
            "This status snapshot is documentation-only. It does not trade, "
            "place orders, call brokers, or approve live trading."
        ),
        "",
    ]
    if result.latest_test_count is not None:
        lines.extend([f"Latest test count: {result.latest_test_count}", ""])

    lines.extend(["## Capabilities", ""])
    lines.extend(f"- {capability}" for capability in result.capabilities)
    lines.extend(["", "## Safety Boundaries", ""])
    lines.extend(f"- {boundary}" for boundary in result.safety_boundaries)
    lines.extend(["", "## Artifact Locations", ""])
    lines.extend(f"- {key}: `{value}`" for key, value in result.artifact_locations.items())
    lines.extend(["", "## Recent Research Runs", ""])
    if result.recent_research_runs:
        for run in result.recent_research_runs:
            lines.append(
                f"- {run.get('run_id', 'unknown')} "
                f"(strategy: {run.get('strategy_id', 'unknown')})"
            )
            for key in (
                "review_status",
                "readiness_status",
                "plan_status",
                "paper_sim_review_status",
                "packet_status",
            ):
                if run.get(key) is not None:
                    lines.append(f"  - {key}: {run[key]}")
    else:
        lines.append("- No recent research runs found.")
    lines.append("")
    return "\n".join(lines)


def _discover_recent_research_runs(
    research_runs_dir: Path,
    max_recent_runs: int,
) -> list[dict[str, Any]]:
    if max_recent_runs <= 0 or not research_runs_dir.exists():
        return []
    run_dirs = [path for path in research_runs_dir.iterdir() if path.is_dir()]
    run_dirs = sorted(
        run_dirs,
        key=lambda path: (
            not (path / "manifest.json").exists(),
            -path.stat().st_mtime_ns,
            path.name,
        ),
    )
    return [_research_run_summary(path) for path in run_dirs[:max_recent_runs]]


def _research_run_summary(run_dir: Path) -> dict[str, Any]:
    manifest_path = run_dir / "manifest.json"
    review_path = run_dir / "review.json"
    readiness_path = run_dir / "paper_sim_readiness.json"
    plan_path = run_dir / "paper_sim_plan.json"
    paper_sim_review_path = run_dir / "paper_simulation" / "paper_sim_review.json"
    packet_manifest_path = run_dir / "artifact_packet" / "packet_manifest.json"

    manifest = _read_json_object(manifest_path)
    review = _read_json_object(review_path)
    readiness = _read_json_object(readiness_path)
    plan = _read_json_object(plan_path)
    paper_sim_review = _read_json_object(paper_sim_review_path)
    packet = _read_json_object(packet_manifest_path)

    return {
        "run_id": str(manifest.get("run_id") or run_dir.name),
        "strategy_id": manifest.get("strategy_id"),
        "manifest_path": str(manifest_path) if manifest_path.exists() else None,
        "review_path": str(review_path) if review_path.exists() else None,
        "readiness_path": str(readiness_path) if readiness_path.exists() else None,
        "plan_path": str(plan_path) if plan_path.exists() else None,
        "paper_sim_review_path": (
            str(paper_sim_review_path) if paper_sim_review_path.exists() else None
        ),
        "packet_manifest_path": (
            str(packet_manifest_path) if packet_manifest_path.exists() else None
        ),
        "review_status": review.get("status"),
        "readiness_status": readiness.get("status"),
        "plan_status": plan.get("status"),
        "paper_sim_review_status": paper_sim_review.get("status"),
        "packet_status": packet.get("status"),
    }


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}
