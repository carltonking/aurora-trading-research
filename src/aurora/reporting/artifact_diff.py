"""Artifact diffing system for tracking changes between runs.

This module provides diff functionality for research artifacts like
backtest results, optimization proposals, and performance metrics.
No live trading, no broker calls, no profitability claims.
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, UTC
from pathlib import Path
from typing import Any


def diff_dicts(old: dict, new: dict, path: str = "") -> dict:
    """Recursively compare two dictionaries and return a structured diff.

    Args:
        old: Previous version of the dictionary.
        new: Current version of the dictionary.
        path: Current path in the nested structure (for nested diffs).

    Returns:
        Dictionary with 'added', 'removed', 'changed', and 'nested' keys
        describing the differences. For numeric changes, includes delta.
    """
    diff: dict[str, Any] = {
        "added": {},
        "removed": {},
        "changed": {},
        "nested": {},
    }

    all_keys = set(old.keys()) | set(new.keys())

    for key in all_keys:
        current_path = f"{path}.{key}" if path else key
        old_val = old.get(key)
        new_val = new.get(key)

        if key not in old:
            diff["added"][key] = new_val
        elif key not in new:
            diff["removed"][key] = old_val
        elif old_val != new_val:
            if isinstance(old_val, (int, float)) and isinstance(new_val, (int, float)):
                delta = new_val - old_val
                diff["changed"][key] = {
                    "old_value": old_val,
                    "new_value": new_val,
                    "delta": delta,
                    "percent_change": (delta / old_val * 100) if old_val != 0 else None,
                }
            elif isinstance(old_val, dict) and isinstance(new_val, dict):
                nested_diff = diff_dicts(old_val, new_val, current_path)
                if any(nested_diff.values()):
                    diff["nested"][key] = nested_diff
            elif isinstance(old_val, list) and isinstance(new_val, list):
                if len(old_val) != len(new_val):
                    diff["changed"][key] = {
                        "old_value": old_val,
                        "new_value": new_val,
                        "length_old": len(old_val),
                        "length_new": len(new_val),
                    }
                else:
                    diff["changed"][key] = {
                        "old_value": old_val,
                        "new_value": new_val,
                    }
            else:
                diff["changed"][key] = {
                    "old_value": old_val,
                    "new_value": new_val,
                }

    return diff


@dataclass
class ArtifactRun:
    """Represents a single artifact run."""

    timestamp: str
    artifact_name: str
    data: dict[str, Any]
    path: str


class ArtifactDiffer:
    """Manages artifact versioning and diffing.

    This class archives previous artifact versions and provides
    diff functionality between runs.
    """

    def __init__(self, artifact_dir: str, diff_dir: str | None = None) -> None:
        """Initialize the artifact differ.

        Args:
            artifact_dir: Directory containing artifacts.
            diff_dir: Directory for storing previous versions. Defaults to artifact_dir/diffs.
        """
        self._artifact_dir = Path(artifact_dir)
        self._diff_dir = Path(diff_dir) if diff_dir else self._artifact_dir / "diffs"
        self._enabled = os.getenv("AURORA_DIFF_ARTIFACTS", "false").lower() == "true"

    @property
    def is_enabled(self) -> bool:
        """Check if diffing is enabled."""
        return self._enabled

    def save_run_artifact(self, artifact_name: str, data: dict[str, Any]) -> Path | None:
        """Save artifact and archive previous version if diffing is enabled.

        Args:
            artifact_name: Name of the artifact (e.g., 'backtest_summary').
            data: Artifact data to save.

        Returns:
            Path to the saved artifact, or None if diffing is disabled.
        """
        if not self._enabled:
            return None

        self._artifact_dir.mkdir(parents=True, exist_ok=True)
        self._diff_dir.mkdir(parents=True, exist_ok=True)

        artifact_path = self._artifact_dir / f"{artifact_name}.json"
        prev_path = self._diff_dir / f"{artifact_name}.prev.json"

        if artifact_path.exists():
            with artifact_path.open("r", encoding="utf-8") as f:
                prev_data = json.load(f)

            with prev_path.open("w", encoding="utf-8") as f:
                json.dump(prev_data, f, indent=2, sort_keys=True)

        with artifact_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)

        return artifact_path

    def get_previous(self, artifact_name: str) -> dict | None:
        """Get the previous version of an artifact.

        Args:
            artifact_name: Name of the artifact.

        Returns:
            Previous artifact data, or None if not available.
        """
        prev_path = self._diff_dir / f"{artifact_name}.prev.json"

        if not prev_path.exists():
            return None

        with prev_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def get_latest(self, artifact_name: str) -> dict | None:
        """Get the latest version of an artifact.

        Args:
            artifact_name: Name of the artifact.

        Returns:
            Latest artifact data, or None if not available.
        """
        artifact_path = self._artifact_dir / f"{artifact_name}.json"

        if not artifact_path.exists():
            return None

        with artifact_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def diff_latest(self, artifact_name: str) -> dict:
        """Compute diff between latest and previous artifact versions.

        Args:
            artifact_name: Name of the artifact.

        Returns:
            Dictionary containing the diff, or {'error': 'no previous version'}
            if no previous version exists.
        """
        latest = self.get_latest(artifact_name)
        previous = self.get_previous(artifact_name)

        if latest is None:
            return {"error": "no latest version"}

        if previous is None:
            return {
                "artifact_name": artifact_name,
                "status": "no_previous",
                "message": "No previous version to compare against",
                "current": latest,
            }

        diff_result = diff_dicts(previous, latest)

        return {
            "artifact_name": artifact_name,
            "generated_at": datetime.now(UTC).isoformat(),
            "diff": diff_result,
            "previous_timestamp": None,
            "latest_timestamp": None,
        }

    def save_diff(self, artifact_name: str, output_path: str) -> Path | None:
        """Save the diff to a file.

        Args:
            artifact_name: Name of the artifact.
            output_path: Path to save the diff JSON.

        Returns:
            Path to the saved diff, or None if diff fails.
        """
        diff_result = self.diff_latest(artifact_name)

        if "error" in diff_result:
            return None

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with output_file.open("w", encoding="utf-8") as f:
            json.dump(diff_result, f, indent=2, sort_keys=True)

        return output_file

    def list_history(self, artifact_name: str) -> list[dict]:
        """List available history for an artifact.

        Args:
            artifact_name: Name of the artifact.

        Returns:
            List of available versions with timestamps.
        """
        history = []

        latest = self.get_latest(artifact_name)
        if latest:
            history.append({
                "version": "latest",
                "timestamp": "current",
                "path": str(self._artifact_dir / f"{artifact_name}.json"),
            })

        previous = self.get_previous(artifact_name)
        if previous:
            history.append({
                "version": "previous",
                "timestamp": "previous",
                "path": str(self._diff_dir / f"{artifact_name}.prev.json"),
            })

        return history


def create_differ(artifact_dir: str | None = None) -> ArtifactDiffer | None:
    """Create an ArtifactDiffer if diffing is enabled.

    Args:
        artifact_dir: Directory for artifacts. Defaults to AURORA_ARTIFACT_DIR env var or 'data'.

    Returns:
        ArtifactDiffer instance if enabled, None otherwise.
    """
    if os.getenv("AURORA_DIFF_ARTIFACTS", "false").lower() != "true":
        return None

    artifact_dir = artifact_dir or os.getenv("AURORA_ARTIFACT_DIR", "data")
    return ArtifactDiffer(artifact_dir)