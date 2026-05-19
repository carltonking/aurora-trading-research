"""Local JSON and Markdown report helpers."""

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from aurora.reporting.exceptions import ReportLoadError, ReportSaveError
from aurora.reporting.summaries import (
    summarize_backtest_metrics,
    summarize_orders,
    summarize_positions,
    summarize_risk_decisions,
)


def save_json_report(data: dict, path: str | Path) -> Path:
    """Save a dictionary report as indented JSON."""
    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with report_path.open("w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, sort_keys=True)
    except OSError as exc:
        raise ReportSaveError(f"Could not save JSON report: {report_path}") from exc
    return report_path


def load_json_report(path: str | Path) -> dict:
    """Load a JSON report from disk."""
    report_path = Path(path)
    if not report_path.exists():
        raise ReportLoadError(f"Report not found: {report_path}")
    try:
        with report_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        raise ReportLoadError(f"Could not load JSON report: {report_path}") from exc
    if not isinstance(data, dict):
        raise ReportLoadError(f"JSON report must contain an object: {report_path}")
    return data


def save_markdown_report(title: str, sections: dict[str, object], path: str | Path) -> Path:
    """Save a simple readable Markdown report."""
    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# {title}", ""]
    for section_title, content in sections.items():
        lines.extend([f"## {section_title}", "", _format_markdown_content(content), ""])
    try:
        report_path.write_text("\n".join(lines), encoding="utf-8")
    except OSError as exc:
        raise ReportSaveError(f"Could not save Markdown report: {report_path}") from exc
    return report_path


def generate_daily_summary_report(
    account: dict | None = None,
    positions: dict | list[dict] | None = None,
    orders: list[dict] | None = None,
    risk_decisions: list[dict] | None = None,
    backtest_metrics: dict | None = None,
) -> dict[str, Any]:
    """Generate a local daily summary report dictionary."""
    return {
        "created_at": datetime.now(UTC).isoformat(),
        "account": account,
        "positions_summary": summarize_positions(positions or {}),
        "orders_summary": summarize_orders(orders or []),
        "risk_summary": summarize_risk_decisions(risk_decisions or []),
        "backtest_summary": summarize_backtest_metrics(backtest_metrics or {}),
    }


class ReportBuilder:
    """Compatibility wrapper for report generation imports."""

    def describe(self) -> str:
        """Return a short description of the component."""
        return "Builds local research reports for strategy validation and monitoring."


def _format_markdown_content(content: object) -> str:
    if isinstance(content, dict):
        return "\n".join(f"- **{key}**: {value}" for key, value in content.items())
    if isinstance(content, list):
        return "\n".join(f"- {item}" for item in content)
    return str(content)
