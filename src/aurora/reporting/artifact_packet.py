"""Research artifact packet builder."""

from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from aurora.reporting.exceptions import AuroraReportingError
from aurora.reporting.reports import save_json_report

ARTIFACT_PACKET_COMPLETE = "COMPLETE"
ARTIFACT_PACKET_PARTIAL = "PARTIAL"
ARTIFACT_PACKET_BLOCKED = "BLOCKED"

PACKET_INFO = "INFO"
PACKET_WARNING = "WARNING"
PACKET_CRITICAL = "CRITICAL"

CORE_ARTIFACTS = [
    "manifest.json",
    "config.json",
    "signals.csv",
    "backtest.json",
    "diagnostics.json",
]
OPTIONAL_ARTIFACTS = [
    "market_data.csv",
    "features.csv",
    "equity_curve.csv",
    "trades.csv",
    "report.md",
    "review.json",
    "paper_sim_readiness.json",
    "paper_sim_plan.json",
    "paper_simulation/paper_sim_review.json",
]
PACKET_SAFETY_FLAGS = {
    "artifact_only": True,
    "placed_orders": False,
    "used_broker": False,
    "wrote_ledger": False,
    "external_llm_calls": False,
}


@dataclass(frozen=True)
class ArtifactPacketFinding:
    """Single deterministic artifact packet finding."""

    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class ArtifactPacketConfig:
    """Configuration for building a local research artifact packet."""

    run_dir: str
    output_dir: str | None = None
    copy_artifacts: bool = True
    require_manifest: bool = True
    require_core_artifacts: bool = True
    include_optional_artifacts: bool = True
    fail_on_missing_core: bool = False
    create_zip: bool = False
    zip_path: str | None = None


@dataclass(frozen=True)
class ArtifactPacketResult:
    """Result from building a research artifact packet."""

    run_id: str
    strategy_id: str
    status: str
    created_at: str
    run_dir: str
    output_dir: str
    packet_manifest_path: str
    included_artifacts: list[dict[str, Any]]
    missing_artifacts: list[str]
    findings: list[ArtifactPacketFinding]
    safety_flags: dict[str, Any]
    zip_path: str | None = None
    zip_sha256: str | None = None
    zip_size_bytes: int | None = None


class ArtifactPacketError(AuroraReportingError):
    """Raised when an artifact packet cannot be built."""


def build_artifact_packet(config: ArtifactPacketConfig) -> ArtifactPacketResult:
    """Build a deterministic local packet from known research run artifacts."""
    run_dir = Path(config.run_dir)
    if not run_dir.exists() or not run_dir.is_dir():
        raise ArtifactPacketError(f"Research run directory not found: {run_dir}")

    manifest_path = run_dir / "manifest.json"
    if config.require_manifest and not manifest_path.exists():
        raise ArtifactPacketError(f"Research run manifest not found: {manifest_path}")

    manifest = _load_manifest(manifest_path) if manifest_path.exists() else {}
    output_dir = Path(config.output_dir) if config.output_dir else run_dir / "artifact_packet"
    output_dir.mkdir(parents=True, exist_ok=True)

    findings: list[ArtifactPacketFinding] = []
    included_artifacts: list[dict[str, Any]] = []
    missing_artifacts: list[str] = []

    for name in _expected_artifacts(config):
        source_path = run_dir / name
        if not _is_safe_run_file(source_path, run_dir) or not source_path.exists():
            missing_artifacts.append(name)
            finding = _missing_artifact_finding(name, config)
            if finding is not None:
                findings.append(finding)
            continue
        included_artifacts.append(
            _include_artifact(source_path, run_dir, output_dir, config.copy_artifacts)
        )

    if config.create_zip and not config.copy_artifacts:
        findings.append(
            ArtifactPacketFinding(
                code="zip_manifest_only",
                severity=PACKET_WARNING,
                message=(
                    "ZIP export requested while copy_artifacts is false; the ZIP contains "
                    "packet_manifest.json with references only."
                ),
            )
        )

    status = _packet_status(findings)
    result = ArtifactPacketResult(
        run_id=str(manifest.get("run_id") or run_dir.name),
        strategy_id=str(manifest.get("strategy_id") or "unknown"),
        status=status,
        created_at=datetime.now(UTC).isoformat(),
        run_dir=str(run_dir),
        output_dir=str(output_dir),
        packet_manifest_path=str(output_dir / "packet_manifest.json"),
        included_artifacts=included_artifacts,
        missing_artifacts=missing_artifacts,
        findings=findings,
        safety_flags=dict(PACKET_SAFETY_FLAGS),
    )
    save_artifact_packet_manifest(result, result.packet_manifest_path)
    if config.create_zip:
        # The ZIP includes packet_manifest.json, while the final on-disk manifest
        # records the ZIP's own hash and size. That self-reference cannot be
        # represented inside the ZIP without changing the ZIP hash, so the ZIP
        # contains the pre-ZIP manifest and the final manifest is rewritten below.
        zip_path = Path(config.zip_path) if config.zip_path else run_dir / "artifact_packet.zip"
        _create_packet_zip(output_dir, zip_path, result.included_artifacts)
        result = replace(
            result,
            zip_path=str(zip_path),
            zip_sha256=_sha256_file(zip_path),
            zip_size_bytes=zip_path.stat().st_size,
        )
        save_artifact_packet_manifest(result, result.packet_manifest_path)
    return result


def artifact_packet_result_to_dict(result: ArtifactPacketResult) -> dict[str, Any]:
    """Convert an artifact packet result to a JSON-serializable dictionary."""
    return asdict(result)


def save_artifact_packet_manifest(result: ArtifactPacketResult, path: str | Path) -> Path:
    """Save an artifact packet manifest."""
    return save_json_report(artifact_packet_result_to_dict(result), path)


def _expected_artifacts(config: ArtifactPacketConfig) -> list[str]:
    artifacts = []
    if config.require_core_artifacts:
        artifacts.extend(CORE_ARTIFACTS if config.require_manifest else CORE_ARTIFACTS[1:])
    elif config.require_manifest:
        artifacts.append("manifest.json")
    if config.include_optional_artifacts:
        artifacts.extend(OPTIONAL_ARTIFACTS)
    return artifacts


def _missing_artifact_finding(
    name: str,
    config: ArtifactPacketConfig,
) -> ArtifactPacketFinding | None:
    if name in CORE_ARTIFACTS and config.require_core_artifacts:
        severity = PACKET_CRITICAL if config.fail_on_missing_core else PACKET_WARNING
        return ArtifactPacketFinding(
            code="missing_core_artifact",
            severity=severity,
            message=f"Core research artifact is missing: {name}.",
        )
    if name in OPTIONAL_ARTIFACTS and config.include_optional_artifacts:
        return ArtifactPacketFinding(
            code="missing_optional_artifact",
            severity=PACKET_WARNING,
            message=f"Optional research artifact is missing: {name}.",
        )
    return None


def _include_artifact(
    source_path: Path,
    run_dir: Path,
    output_dir: Path,
    copy_artifacts: bool,
) -> dict[str, Any]:
    artifact_name = source_path.relative_to(run_dir).as_posix()
    packet_path = None
    if copy_artifacts:
        destination = output_dir / artifact_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source_path.resolve() != destination.resolve():
            shutil.copy2(source_path, destination)
        packet_path = str(destination)
    return {
        "name": artifact_name,
        "source_path": str(source_path),
        "packet_path": packet_path,
        "size_bytes": source_path.stat().st_size,
        "sha256": _sha256_file(source_path),
    }


def _packet_status(findings: list[ArtifactPacketFinding]) -> str:
    if any(finding.severity == PACKET_CRITICAL for finding in findings):
        return ARTIFACT_PACKET_BLOCKED
    if any(finding.severity == PACKET_WARNING for finding in findings):
        return ARTIFACT_PACKET_PARTIAL
    return ARTIFACT_PACKET_COMPLETE


def _create_packet_zip(
    output_dir: Path,
    zip_path: Path,
    included_artifacts: list[dict[str, Any]],
) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    files = _packet_zip_files(output_dir, included_artifacts)
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as archive:
        for path in files:
            relative_path = path.relative_to(output_dir).as_posix()
            info = ZipInfo(relative_path)
            info.compress_type = ZIP_DEFLATED
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())


def _packet_zip_files(
    output_dir: Path,
    included_artifacts: list[dict[str, Any]],
) -> list[Path]:
    files = []
    resolved_output_dir = output_dir.resolve()
    allowed_paths = _allowed_zip_paths(output_dir, included_artifacts)
    for path in allowed_paths:
        if not path.exists() or not path.is_file():
            continue
        try:
            path.resolve().relative_to(resolved_output_dir)
        except ValueError:
            continue
        if _exclude_from_zip(path, output_dir):
            continue
        files.append(path)
    return sorted(files, key=lambda item: item.relative_to(output_dir).as_posix())


def _allowed_zip_paths(
    output_dir: Path,
    included_artifacts: list[dict[str, Any]],
) -> list[Path]:
    paths = [output_dir / "packet_manifest.json"]
    for artifact in included_artifacts:
        packet_path = artifact.get("packet_path")
        if packet_path:
            paths.append(Path(str(packet_path)))
    return paths


def _exclude_from_zip(path: Path, output_dir: Path) -> bool:
    relative_parts = path.relative_to(output_dir).parts
    if any(part.startswith(".") for part in relative_parts):
        return True
    if any(part == "__pycache__" for part in relative_parts):
        return True
    if path.suffix.lower() in {".zip", ".pyc", ".pyo"}:
        return True
    if any(part.endswith("_cache") or part == "cache" for part in relative_parts):
        return True
    return False


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactPacketError(f"Could not read research run manifest: {path}") from exc
    if not isinstance(data, dict):
        raise ArtifactPacketError(f"Research run manifest must contain an object: {path}")
    return data


def _is_safe_run_file(path: Path, run_dir: Path) -> bool:
    try:
        resolved_path = path.resolve()
        resolved_run_dir = run_dir.resolve()
    except OSError:
        return False
    try:
        resolved_path.relative_to(resolved_run_dir)
    except ValueError:
        return False
    return resolved_path.is_file()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
