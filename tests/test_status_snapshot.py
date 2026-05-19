import json
from pathlib import Path

from typer.testing import CliRunner

from aurora.cli.app import app
from aurora.reporting.status_snapshot import (
    ProjectStatusSnapshotConfig,
    create_project_status_snapshot,
    project_status_snapshot_result_to_dict,
    render_project_status_markdown,
)


def test_status_snapshot_writes_json_and_markdown(tmp_path) -> None:
    output_dir = tmp_path / "data" / "status"

    result = create_project_status_snapshot(
        ProjectStatusSnapshotConfig(output_dir=str(output_dir), latest_test_count=213)
    )

    assert Path(result.json_path).exists()
    assert Path(result.markdown_path).exists()


def test_status_snapshot_json_contains_safety_flags(tmp_path) -> None:
    result = create_project_status_snapshot(
        ProjectStatusSnapshotConfig(output_dir=str(tmp_path / "status"))
    )

    payload = json.loads(Path(result.json_path).read_text(encoding="utf-8"))

    assert payload["safety_flags"]["status_snapshot_only"] is True
    assert payload["safety_flags"]["placed_orders"] is False
    assert payload["safety_flags"]["used_broker"] is False
    assert payload["safety_flags"]["wrote_ledger"] is False
    assert payload["safety_flags"]["external_llm_calls"] is False


def test_status_snapshot_markdown_contains_safety_statement(tmp_path) -> None:
    result = create_project_status_snapshot(
        ProjectStatusSnapshotConfig(output_dir=str(tmp_path / "status"))
    )

    markdown = Path(result.markdown_path).read_text(encoding="utf-8")

    assert (
        "This status snapshot is documentation-only. It does not trade, place orders, "
        "call brokers, or approve live trading."
    ) in markdown


def test_missing_research_runs_dir_returns_empty_recent_runs(tmp_path) -> None:
    result = create_project_status_snapshot(
        ProjectStatusSnapshotConfig(
            output_dir=str(tmp_path / "status"),
            research_runs_dir=str(tmp_path / "missing_runs"),
        )
    )

    assert result.recent_research_runs == []


def test_recent_research_runs_are_discovered_from_manifest(tmp_path) -> None:
    research_runs_dir = tmp_path / "data" / "research_runs"
    _write_run(research_runs_dir / "run_1", strategy_id="strategy_1")

    result = create_project_status_snapshot(
        ProjectStatusSnapshotConfig(
            output_dir=str(tmp_path / "status"),
            research_runs_dir=str(research_runs_dir),
        )
    )

    assert len(result.recent_research_runs) == 1
    assert result.recent_research_runs[0]["run_id"] == "run_1"
    assert result.recent_research_runs[0]["strategy_id"] == "strategy_1"
    assert result.recent_research_runs[0]["manifest_path"] == str(
        research_runs_dir / "run_1" / "manifest.json"
    )


def test_recent_research_run_status_hints_are_included(tmp_path) -> None:
    research_runs_dir = tmp_path / "data" / "research_runs"
    run_dir = _write_run(research_runs_dir / "run_1")
    _write_json(run_dir / "review.json", {"status": "APPROVED_FOR_PAPER_SIMULATION"})
    _write_json(run_dir / "paper_sim_readiness.json", {"status": "READY_FOR_PAPER_SIMULATION"})
    _write_json(run_dir / "paper_sim_plan.json", {"status": "PLAN_READY"})
    paper_sim_dir = run_dir / "paper_simulation"
    paper_sim_dir.mkdir()
    _write_json(paper_sim_dir / "paper_sim_review.json", {"status": "PASS"})
    packet_dir = run_dir / "artifact_packet"
    packet_dir.mkdir()
    _write_json(packet_dir / "packet_manifest.json", {"status": "COMPLETE"})

    result = create_project_status_snapshot(
        ProjectStatusSnapshotConfig(
            output_dir=str(tmp_path / "status"),
            research_runs_dir=str(research_runs_dir),
        )
    )

    run = result.recent_research_runs[0]
    assert run["review_status"] == "APPROVED_FOR_PAPER_SIMULATION"
    assert run["readiness_status"] == "READY_FOR_PAPER_SIMULATION"
    assert run["plan_status"] == "PLAN_READY"
    assert run["paper_sim_review_status"] == "PASS"
    assert run["packet_status"] == "COMPLETE"
    assert run["paper_sim_review_path"] == str(paper_sim_dir / "paper_sim_review.json")
    assert run["packet_manifest_path"] == str(packet_dir / "packet_manifest.json")


def test_max_recent_runs_is_respected(tmp_path) -> None:
    research_runs_dir = tmp_path / "data" / "research_runs"
    _write_run(research_runs_dir / "run_1")
    _write_run(research_runs_dir / "run_2")
    _write_run(research_runs_dir / "run_3")

    result = create_project_status_snapshot(
        ProjectStatusSnapshotConfig(
            output_dir=str(tmp_path / "status"),
            research_runs_dir=str(research_runs_dir),
            max_recent_runs=2,
        )
    )

    assert len(result.recent_research_runs) == 2


def test_project_status_snapshot_result_to_dict_is_json_serializable(tmp_path) -> None:
    result = create_project_status_snapshot(
        ProjectStatusSnapshotConfig(output_dir=str(tmp_path / "status"), latest_test_count=213)
    )

    payload = project_status_snapshot_result_to_dict(result)
    encoded = json.dumps(payload)

    assert "status_snapshot_only" in encoded
    assert "213" in encoded


def test_render_project_status_markdown_includes_required_sections(tmp_path) -> None:
    result = create_project_status_snapshot(
        ProjectStatusSnapshotConfig(output_dir=str(tmp_path / "status"))
    )

    markdown = render_project_status_markdown(result)

    assert "# AURORA Trading Research Project Status" in markdown
    assert "## Capabilities" in markdown
    assert "## Safety Boundaries" in markdown
    assert "## Artifact Locations" in markdown
    assert "## Recent Research Runs" in markdown


def test_cli_reports_status_smoke(tmp_path) -> None:
    output_dir = tmp_path / "data" / "status"
    research_runs_dir = tmp_path / "data" / "research_runs"
    _write_run(research_runs_dir / "run_1")
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "reports",
            "status",
            "--output-dir",
            str(output_dir),
            "--research-runs-dir",
            str(research_runs_dir),
            "--latest-test-count",
            "213",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Status snapshot is documentation-only" in result.output
    assert "project_status.json" in result.output
    assert "project_status.md" in result.output


def test_status_snapshot_does_not_create_ledger_files(tmp_path) -> None:
    create_project_status_snapshot(
        ProjectStatusSnapshotConfig(output_dir=str(tmp_path / "data" / "status"))
    )

    ledger_dir = tmp_path / "data" / "ledger"
    assert not (ledger_dir / "orders.jsonl").exists()
    assert not (ledger_dir / "risk_decisions.jsonl").exists()
    assert not (ledger_dir / "account.json").exists()
    assert not (ledger_dir / "positions.json").exists()


def _write_run(run_dir: Path, strategy_id: str = "strategy_1") -> Path:
    run_dir.mkdir(parents=True)
    _write_json(
        run_dir / "manifest.json",
        {
            "run_id": run_dir.name,
            "strategy_id": strategy_id,
            "safety_flags": {
                "research_only": True,
                "placed_orders": False,
                "used_broker": False,
                "wrote_ledger": False,
                "external_llm_calls": False,
            },
        },
    )
    return run_dir


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")
