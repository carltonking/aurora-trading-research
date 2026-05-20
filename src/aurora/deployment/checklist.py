"""Deployment readiness checklist for AURORA strategies.

This module provides a checklist to verify safety gates, disclosure
requirements, and export integrity before strategy deployment.
"""

from __future__ import annotations

import json
import os
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

import yaml


MANDATORY_DISCLAIMER = (
    "This checklist is an advisory tool only. AURORA does not guarantee "
    "the safety or profitability of any strategy. The decision to deploy "
    "is entirely the user's responsibility. Past performance does not "
    "guarantee future results."
)

DEFAULT_CHECKLIST = """# AURORA Deployment Readiness Checklist
# This is a research-only advisory checklist.

checklist:
  - id: risk_killswitch_configured
    category: risk
    description: "Kill-switch triggers are configured"
    type: boolean

  - id: risk_portfolio_limits_set
    category: risk
    description: "Portfolio risk limits are set (max drawdown, daily loss)"
    type: boolean

  - id: risk_position_sizing_configured
    category: risk
    description: "Position sizing parameters are configured"
    type: boolean

  - id: perf_sharpe_positive
    category: performance
    description: "Sharpe ratio is positive"
    type: threshold
    params:
      metric: sharpe_ratio
      operator: gt
      value: 0

  - id: perf_win_rate_acceptable
    category: performance
    description: "Win rate is above 40%"
    type: threshold
    params:
      metric: win_rate
      operator: gte
      value: 0.4

  - id: perf_max_drawdown_acceptable
    category: performance
    description: "Max drawdown is under 30%"
    type: threshold
    params:
      metric: max_drawdown
      operator: lt
      value: 0.3

  - id: doc_readiness_report_exists
    category: documentation
    description: "Readiness report has been generated"
    type: file_exists
    params:
      path: "readiness_report.json"

  - id: doc_safety_audit_run
    category: documentation
    description: "Safety audit has been run with no critical failures"
    type: boolean

  - id: doc_disclaimer_acknowledged
    category: legal
    description: "User acknowledges mandatory disclaimers"
    type: confirmation
    prompt: "Do you acknowledge that this is research-only and you bear all responsibility for trading decisions?"

  - id: export_no_secrets
    category: export
    description: "Export bundle contains no API keys or secrets"
    type: boolean

  - id: export_strategy_file_present
    category: export
    description: "Strategy file exists in export bundle"
    type: file_exists
    params:
      path: "strategy.py"

  - id: export_config_valid
    category: export
    description: "Export configuration is valid"
    type: boolean
"""


@dataclass
class ChecklistItem:
    """A single checklist item."""

    id: str
    category: str
    description: str
    type: str
    params: dict[str, Any] = field(default_factory=dict)
    prompt: Optional[str] = None


@dataclass
class ChecklistResult:
    """Result of a single checklist check."""

    item_id: str
    passed: bool
    details: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class DeploymentChecklist:
    """Deployment readiness checklist runner."""

    def __init__(self, checklist_path: Optional[str] = None) -> None:
        """Initialize the checklist.

        Args:
            checklist_path: Path to YAML checklist definition. Uses default if None.
        """
        self._items: list[ChecklistItem] = []

        if checklist_path and os.path.exists(checklist_path):
            self._load_from_file(checklist_path)
        else:
            self._load_default()

    def _load_default(self) -> None:
        """Load the default checklist."""
        self._load_from_string(DEFAULT_CHECKLIST)

    def _load_from_file(self, path: str) -> None:
        """Load checklist from file."""
        with open(path, "r", encoding="utf-8") as f:
            self._load_from_string(f.read())

    def _load_from_string(self, yaml_content: str) -> None:
        """Load checklist from YAML string."""
        data = yaml.safe_load(yaml_content)
        checklist_data = data.get("checklist", [])

        for item_data in checklist_data:
            self._items.append(
                ChecklistItem(
                    id=item_data["id"],
                    category=item_data["category"],
                    description=item_data["description"],
                    type=item_data["type"],
                    params=item_data.get("params", {}),
                    prompt=item_data.get("prompt"),
                )
            )

    @property
    def items(self) -> list[ChecklistItem]:
        """Get all checklist items."""
        return self._items

    def run(
        self,
        export_bundle_path: Optional[str] = None,
        readiness_report_path: Optional[str] = None,
        strategy_metrics: Optional[dict[str, Any]] = None,
        answers: Optional[dict[str, bool]] = None,
    ) -> list[ChecklistResult]:
        """Run the checklist.

        Args:
            export_bundle_path: Path to export ZIP file.
            readiness_report_path: Path to readiness report JSON.
            strategy_metrics: Dictionary of strategy performance metrics.
            answers: Pre-answered boolean values (for non-interactive mode).

        Returns:
            List of checklist results.
        """
        results = []
        strategy_metrics = strategy_metrics or {}
        answers = answers or {}

        for item in self._items:
            result = self._run_item(
                item,
                export_bundle_path,
                readiness_report_path,
                strategy_metrics,
                answers.get(item.id),
            )
            results.append(result)

        return results

    def _run_item(
        self,
        item: ChecklistItem,
        export_bundle_path: Optional[str],
        readiness_report_path: Optional[str],
        strategy_metrics: dict[str, Any],
        pre_answer: Optional[bool],
    ) -> ChecklistResult:
        """Run a single checklist item."""
        try:
            if item.type == "boolean":
                return self._run_boolean(item, pre_answer)
            elif item.type == "threshold":
                return self._run_threshold(item, strategy_metrics)
            elif item.type == "confirmation":
                return self._run_confirmation(item, pre_answer)
            elif item.type == "file_exists":
                return self._run_file_exists(item, export_bundle_path)
            else:
                return ChecklistResult(
                    item_id=item.id,
                    passed=False,
                    details=f"Unknown check type: {item.type}",
                )
        except Exception as e:
            return ChecklistResult(
                item_id=item.id,
                passed=False,
                details=f"Error: {str(e)}",
            )

    def _run_boolean(
        self,
        item: ChecklistItem,
        pre_answer: Optional[bool],
    ) -> ChecklistResult:
        """Run a boolean check."""
        if pre_answer is not None:
            passed = pre_answer
            details = "Pre-answered" if passed else "User indicated not configured"
        else:
            details = "(Run with --answers flag to provide answers)"

        return ChecklistResult(
            item_id=item.id,
            passed=bool(pre_answer),
            details=details,
        )

    def _run_threshold(
        self,
        item: ChecklistItem,
        strategy_metrics: dict[str, Any],
    ) -> ChecklistResult:
        """Run a threshold check."""
        params = item.params
        metric = params.get("metric")
        operator = params.get("operator")
        threshold = params.get("value")

        if metric not in strategy_metrics:
            return ChecklistResult(
                item_id=item.id,
                passed=False,
                details=f"Metric '{metric}' not found in strategy metrics",
            )

        actual_value = strategy_metrics[metric]
        passed = self._compare_values(actual_value, operator, threshold)

        return ChecklistResult(
            item_id=item.id,
            passed=passed,
            details=f"{metric}={actual_value} ({'passed' if passed else 'failed'}, threshold: {operator} {threshold})",
        )

    def _compare_values(self, actual: Any, operator: str, threshold: Any) -> bool:
        """Compare actual value against threshold."""
        if operator == "gt":
            return actual > threshold
        elif operator == "gte":
            return actual >= threshold
        elif operator == "lt":
            return actual < threshold
        elif operator == "lte":
            return actual <= threshold
        elif operator == "eq":
            return actual == threshold
        return False

    def _run_confirmation(
        self,
        item: ChecklistItem,
        pre_answer: Optional[bool],
    ) -> ChecklistResult:
        """Run a confirmation check."""
        if pre_answer is not None:
            passed = pre_answer
            details = "User acknowledged" if passed else "User did not acknowledge"
        else:
            details = f"Prompt: {item.prompt} (Run with --answers to confirm)"

        return ChecklistResult(
            item_id=item.id,
            passed=bool(pre_answer),
            details=details,
        )

    def _run_file_exists(
        self,
        item: ChecklistItem,
        export_bundle_path: Optional[str],
    ) -> ChecklistResult:
        """Run a file exists check."""
        if not export_bundle_path:
            return ChecklistResult(
                item_id=item.id,
                passed=False,
                details="No export bundle provided",
            )

        target_path = item.params.get("path", "")

        try:
            with zipfile.ZipFile(export_bundle_path, "r") as zf:
                file_list = zf.namelist()
                passed = target_path in file_list

                if passed:
                    details = f"Found: {target_path}"
                else:
                    details = f"Not found: {target_path} (available: {', '.join(file_list[:5])}...)"

        except Exception as e:
            return ChecklistResult(
                item_id=item.id,
                passed=False,
                details=f"Error checking bundle: {str(e)}",
            )

        return ChecklistResult(
            item_id=item.id,
            passed=passed,
            details=details,
        )

    def is_ready(self, results: list[ChecklistResult]) -> bool:
        """Check if all items passed.

        Args:
            results: List of checklist results.

        Returns:
            True if all checks passed.
        """
        return all(r.passed for r in results)

    def generate_report(
        self,
        results: list[ChecklistResult],
        output_path: str,
    ) -> None:
        """Generate a JSON report of the checklist run.

        Args:
            results: List of checklist results.
            output_path: Path to save the report.
        """
        report = {
            "generated_at": datetime.now(UTC).isoformat(),
            "mandatory_disclaimer": MANDATORY_DISCLAIMER,
            "total_items": len(results),
            "passed": sum(1 for r in results if r.passed),
            "failed": sum(1 for r in results if not r.passed),
            "results": [
                {
                    "item_id": r.item_id,
                    "passed": r.passed,
                    "details": r.details,
                    "timestamp": r.timestamp,
                }
                for r in results
            ],
        }

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with output_file.open("w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)


def create_default_checklist_file(path: str) -> None:
    """Create a default checklist YAML file.

    Args:
        path: Path to save the checklist.
    """
    with open(path, "w", encoding="utf-8") as f:
        f.write(DEFAULT_CHECKLIST)