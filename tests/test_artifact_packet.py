import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import pytest
from typer.testing import CliRunner

from aurora.cli.app import app
from aurora.reporting.artifact_packet import (
    ARTIFACT_PACKET_BLOCKED,
    ARTIFACT_PACKET_COMPLETE,
    ARTIFACT_PACKET_PARTIAL,
    PACKET_CRITICAL,
    ArtifactPacketConfig,
    ArtifactPacketError,
    artifact_packet_result_to_dict,
    build_artifact_packet,
)


def test_missing_run_dir_raises_artifact_packet_error(tmp_path) -> None:
    with pytest.raises(ArtifactPacketError, match="Research run directory not found"):
        build_artifact_packet(ArtifactPacketConfig(run_dir=str(tmp_path / "missing")))


def test_missing_manifest_required_raises_artifact_packet_error(tmp_path) -> None:
    run_dir = tmp_path / "data" / "research_runs" / "run_1"
    run_dir.mkdir(parents=True)

    with pytest.raises(ArtifactPacketError, match="manifest not found"):
        build_artifact_packet(ArtifactPacketConfig(run_dir=str(run_dir)))


def test_missing_manifest_not_required_can_complete_with_other_core_artifacts(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path, missing={"manifest.json"})

    result = build_artifact_packet(
        ArtifactPacketConfig(
            run_dir=str(run_dir),
            require_manifest=False,
            include_optional_artifacts=False,
        )
    )

    assert result.status == ARTIFACT_PACKET_COMPLETE
    assert result.run_id == "run_1"
    assert result.strategy_id == "unknown"
    assert "manifest.json" not in result.missing_artifacts


def test_complete_artifact_set_produces_complete(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path)

    result = build_artifact_packet(ArtifactPacketConfig(run_dir=str(run_dir)))

    assert result.status == ARTIFACT_PACKET_COMPLETE
    assert result.run_id == "run_1"
    assert result.strategy_id == "strategy_1"
    assert result.missing_artifacts == []
    assert result.zip_path is None
    assert result.zip_sha256 is None
    assert result.zip_size_bytes is None


def test_missing_core_artifact_with_fail_false_produces_partial(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path, missing={"signals.csv"})

    result = build_artifact_packet(
        ArtifactPacketConfig(run_dir=str(run_dir), include_optional_artifacts=False)
    )

    assert result.status == ARTIFACT_PACKET_PARTIAL
    assert "signals.csv" in result.missing_artifacts
    assert _has_finding(result, "missing_core_artifact")


def test_missing_core_artifact_with_fail_true_blocks(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path, missing={"signals.csv"})

    result = build_artifact_packet(
        ArtifactPacketConfig(
            run_dir=str(run_dir),
            include_optional_artifacts=False,
            fail_on_missing_core=True,
        )
    )

    assert result.status == ARTIFACT_PACKET_BLOCKED
    assert "signals.csv" in result.missing_artifacts
    assert _has_finding(result, "missing_core_artifact", PACKET_CRITICAL)


def test_missing_optional_artifact_produces_partial_when_optional_included(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path, missing={"features.csv"})

    result = build_artifact_packet(ArtifactPacketConfig(run_dir=str(run_dir)))

    assert result.status == ARTIFACT_PACKET_PARTIAL
    assert "features.csv" in result.missing_artifacts
    assert _has_finding(result, "missing_optional_artifact")


def test_missing_optional_artifact_does_not_block_complete_when_optional_excluded(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path, missing={"features.csv"})

    result = build_artifact_packet(
        ArtifactPacketConfig(
            run_dir=str(run_dir),
            include_optional_artifacts=False,
        )
    )

    assert result.status == ARTIFACT_PACKET_COMPLETE
    assert "features.csv" not in result.missing_artifacts


def test_copy_artifacts_true_copies_expected_files_to_packet_dir(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path)

    result = build_artifact_packet(
        ArtifactPacketConfig(run_dir=str(run_dir), include_optional_artifacts=False)
    )

    packet_dir = run_dir / "artifact_packet"
    assert (packet_dir / "manifest.json").exists()
    assert (packet_dir / "signals.csv").exists()
    assert all(Path(artifact["packet_path"]).exists() for artifact in result.included_artifacts)


def test_copy_artifacts_false_references_source_paths_without_copying(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path)

    result = build_artifact_packet(
        ArtifactPacketConfig(
            run_dir=str(run_dir),
            copy_artifacts=False,
            include_optional_artifacts=False,
        )
    )

    packet_dir = run_dir / "artifact_packet"
    assert (packet_dir / "packet_manifest.json").exists()
    assert not (packet_dir / "signals.csv").exists()
    assert all(artifact["packet_path"] is None for artifact in result.included_artifacts)
    assert all(Path(artifact["source_path"]).exists() for artifact in result.included_artifacts)


def test_packet_manifest_json_is_written(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path)

    result = build_artifact_packet(
        ArtifactPacketConfig(run_dir=str(run_dir), include_optional_artifacts=False)
    )

    manifest_path = run_dir / "artifact_packet" / "packet_manifest.json"
    assert result.packet_manifest_path == str(manifest_path)
    assert manifest_path.exists()
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["status"] == result.status


def test_included_artifacts_have_size_and_sha256(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path)

    result = build_artifact_packet(
        ArtifactPacketConfig(run_dir=str(run_dir), include_optional_artifacts=False)
    )

    signals_artifact = _artifact_by_name(result, "signals.csv")
    signals_path = run_dir / "signals.csv"
    assert signals_artifact["size_bytes"] == signals_path.stat().st_size
    assert signals_artifact["sha256"] == _sha256(signals_path)


def test_optional_paper_sim_review_artifact_is_included_when_present(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path)

    result = build_artifact_packet(ArtifactPacketConfig(run_dir=str(run_dir)))

    artifact = _artifact_by_name(result, "paper_simulation/paper_sim_review.json")
    source_path = run_dir / "paper_simulation" / "paper_sim_review.json"
    packet_path = run_dir / "artifact_packet" / "paper_simulation" / "paper_sim_review.json"
    assert artifact["source_path"] == str(source_path)
    assert artifact["packet_path"] == str(packet_path)
    assert packet_path.exists()
    assert artifact["size_bytes"] == source_path.stat().st_size
    assert artifact["sha256"] == _sha256(source_path)


def test_artifact_packet_result_to_dict_is_json_serializable(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path)
    result = build_artifact_packet(
        ArtifactPacketConfig(
            run_dir=str(run_dir),
            include_optional_artifacts=False,
            create_zip=True,
        )
    )

    payload = artifact_packet_result_to_dict(result)
    encoded = json.dumps(payload)

    assert "packet_manifest.json" in encoded
    assert "artifact_only" in encoded
    assert "zip_sha256" in encoded


def test_create_zip_true_creates_default_zip_with_manifest(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path)

    result = build_artifact_packet(
        ArtifactPacketConfig(
            run_dir=str(run_dir),
            include_optional_artifacts=False,
            create_zip=True,
        )
    )

    zip_path = run_dir / "artifact_packet.zip"
    assert result.zip_path == str(zip_path)
    assert zip_path.exists()
    assert result.zip_sha256 == _sha256(zip_path)
    assert result.zip_size_bytes == zip_path.stat().st_size
    assert result.zip_size_bytes > 0
    with ZipFile(zip_path) as archive:
        names = archive.namelist()
    assert "packet_manifest.json" in names


def test_zip_includes_paper_sim_review_when_present(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path)

    result = build_artifact_packet(ArtifactPacketConfig(run_dir=str(run_dir), create_zip=True))

    with ZipFile(result.zip_path) as archive:
        names = archive.namelist()

    assert "paper_simulation/paper_sim_review.json" in names


def test_zip_uses_relative_paths_and_excludes_outside_files(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path)
    (run_dir / "outside.txt").write_text("not in packet", encoding="utf-8")

    result = build_artifact_packet(
        ArtifactPacketConfig(
            run_dir=str(run_dir),
            include_optional_artifacts=False,
            create_zip=True,
        )
    )

    with ZipFile(result.zip_path) as archive:
        names = archive.namelist()

    assert names == sorted(names)
    assert all(not name.startswith("/") for name in names)
    assert all(".." not in Path(name).parts for name in names)
    assert "outside.txt" not in names
    assert "manifest.json" in names
    assert "signals.csv" in names


def test_zip_excludes_hidden_cache_and_zip_files_from_packet_dir(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path)
    packet_dir = run_dir / "artifact_packet"
    packet_dir.mkdir()
    (packet_dir / ".hidden").write_text("hidden", encoding="utf-8")
    (packet_dir / "stale.txt").write_text("stale", encoding="utf-8")
    (packet_dir / "old.zip").write_text("zip", encoding="utf-8")
    cache_dir = packet_dir / "__pycache__"
    cache_dir.mkdir()
    (cache_dir / "module.pyc").write_bytes(b"cache")

    result = build_artifact_packet(
        ArtifactPacketConfig(
            run_dir=str(run_dir),
            include_optional_artifacts=False,
            create_zip=True,
        )
    )

    with ZipFile(result.zip_path) as archive:
        names = archive.namelist()

    assert ".hidden" not in names
    assert "stale.txt" not in names
    assert "old.zip" not in names
    assert all("__pycache__" not in name for name in names)


def test_packet_manifest_on_disk_includes_zip_metadata(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path)

    result = build_artifact_packet(
        ArtifactPacketConfig(
            run_dir=str(run_dir),
            include_optional_artifacts=False,
            create_zip=True,
        )
    )

    manifest = json.loads(Path(result.packet_manifest_path).read_text(encoding="utf-8"))
    assert manifest["zip_path"] == result.zip_path
    assert manifest["zip_sha256"] == result.zip_sha256
    assert manifest["zip_size_bytes"] == result.zip_size_bytes


def test_copy_false_create_zip_writes_manifest_only_zip_and_warning(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path)

    result = build_artifact_packet(
        ArtifactPacketConfig(
            run_dir=str(run_dir),
            copy_artifacts=False,
            include_optional_artifacts=False,
            create_zip=True,
        )
    )

    assert result.status == ARTIFACT_PACKET_PARTIAL
    assert _has_finding(result, "zip_manifest_only")
    with ZipFile(result.zip_path) as archive:
        assert archive.namelist() == ["packet_manifest.json"]


def test_cli_reports_packet_smoke(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "reports",
            "packet",
            "--run-dir",
            str(run_dir),
            "--no-include-optional-artifacts",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Artifact packet building only copies local research artifacts" in result.output
    assert "COMPLETE" in result.output
    assert "packet_manifest.json" in result.output


def test_cli_reports_packet_create_zip_smoke(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "reports",
            "packet",
            "--run-dir",
            str(run_dir),
            "--no-include-optional-artifacts",
            "--create-zip",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Packet ZIP:" in result.output
    assert "Packet ZIP sha256:" in result.output
    assert (run_dir / "artifact_packet.zip").exists()


def test_packet_builder_does_not_create_ledger_files(tmp_path) -> None:
    run_dir = _write_run_artifacts(tmp_path)

    build_artifact_packet(ArtifactPacketConfig(run_dir=str(run_dir), create_zip=True))

    ledger_dir = tmp_path / "data" / "ledger"
    assert not (ledger_dir / "orders.jsonl").exists()
    assert not (ledger_dir / "risk_decisions.jsonl").exists()
    assert not (ledger_dir / "account.json").exists()
    assert not (ledger_dir / "positions.json").exists()


def _write_run_artifacts(tmp_path, missing: set[str] | None = None) -> Path:
    missing = missing or set()
    run_dir = tmp_path / "data" / "research_runs" / "run_1"
    run_dir.mkdir(parents=True)

    artifacts = {
        "manifest.json": {
            "run_id": "run_1",
            "strategy_id": "strategy_1",
            "safety_flags": {
                "research_only": True,
                "placed_orders": False,
                "used_broker": False,
                "wrote_ledger": False,
                "external_llm_calls": False,
            },
        },
        "config.json": {"strategy_id": "strategy_1"},
        "backtest.json": {"metrics": {"trade_count": 80}},
        "diagnostics.json": {"ok": True, "issues": [], "summary": {}},
        "review.json": {"status": "APPROVED_FOR_PAPER_SIMULATION"},
        "paper_sim_readiness.json": {"status": "READY_FOR_PAPER_SIMULATION"},
        "paper_sim_plan.json": {"status": "PLAN_READY"},
        "paper_simulation/paper_sim_review.json": {"status": "PASS"},
    }
    csv_artifacts = {
        "market_data.csv": "timestamp,symbol,close\n2024-01-01,SPY,100\n",
        "features.csv": "timestamp,symbol,return_1d\n2024-01-01,SPY,0.01\n",
        "signals.csv": "timestamp,symbol,signal\n2024-01-01,SPY,1\n",
        "equity_curve.csv": "timestamp,equity\n2024-01-01,100000\n",
        "trades.csv": "trade_id,symbol,net_pnl\ntrade_1,SPY,100\n",
    }

    for name, data in artifacts.items():
        if name not in missing:
            _write_json(run_dir / name, data)
    for name, content in csv_artifacts.items():
        if name not in missing:
            (run_dir / name).write_text(content, encoding="utf-8")
    if "report.md" not in missing:
        (run_dir / "report.md").write_text("# Research Report\n", encoding="utf-8")

    return run_dir


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact_by_name(result, name: str) -> dict:
    for artifact in result.included_artifacts:
        if artifact["name"] == name:
            return artifact
    raise AssertionError(f"Artifact not found: {name}")


def _has_finding(result, code: str, severity: str | None = None) -> bool:
    return any(
        finding.code == code and (severity is None or finding.severity == severity)
        for finding in result.findings
    )
