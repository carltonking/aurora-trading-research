"""Serialization helpers for validation reports."""

from dataclasses import asdict
import json
from pathlib import Path

from aurora.validation.overfitting import OverfittingReport
from aurora.validation.walk_forward import WalkForwardResult


def walk_forward_result_to_dict(result: WalkForwardResult) -> dict:
    """Convert a walk-forward result to a JSON-serializable dictionary."""
    return asdict(result)


def overfitting_report_to_dict(report: OverfittingReport) -> dict:
    """Convert an overfitting report to a JSON-serializable dictionary."""
    return asdict(report)


def save_validation_report(data: dict, path: str | Path) -> Path:
    """Save a validation report dictionary to JSON."""
    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, sort_keys=True)
    return report_path


def load_validation_report(path: str | Path) -> dict:
    """Load a validation report JSON file."""
    report_path = Path(path)
    with report_path.open("r", encoding="utf-8") as file:
        return json.load(file)
