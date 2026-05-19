"""Adaptive strategy optimizer for research-only parameter tuning.

This optimizer reads research artifacts and proposes parameter adjustments.
It never trades, never calls brokers, and never claims profitability.
"""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


OPTIMIZER_VERSION = "0.1.0"


@dataclass
class OptimizationProposal:
    """Proposal for strategy parameter changes."""

    strategy_name: str
    status: str
    parameter_changes: dict[str, Any] = field(default_factory=dict)
    rationale: str = ""
    based_on_artifacts: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    optimizer_version: str = OPTIMIZER_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_name": self.strategy_name,
            "status": self.status,
            "parameter_changes": self.parameter_changes,
            "rationale": self.rationale,
            "based_on_artifacts": self.based_on_artifacts,
            "timestamp": self.timestamp,
            "optimizer_version": self.optimizer_version,
        }


class AdaptiveOptimizer:
    """Research-only optimizer that proposes parameter adjustments.

    This optimizer reads research artifacts and makes deterministic
    proposals based on simple rules. It never trades or calls brokers.
    """

    STATUS_REJECTED = "REJECTED"
    STATUS_NEEDS_MORE_RESEARCH = "NEEDS_MORE_RESEARCH"
    STATUS_PROPOSED_FOR_REVIEW = "PROPOSED_FOR_REVIEW"

    DIAGNOSTIC_THRESHOLDS = {
        "min_sharpe_ratio": 0.5,
        "max_drawdown": 0.3,
        "min_win_rate": 0.4,
    }

    def __init__(
        self,
        artifact_directory: str,
        allowed_statuses: list[str] | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.artifact_directory = Path(artifact_directory)
        self.allowed_statuses = allowed_statuses or [self.STATUS_PROPOSED_FOR_REVIEW]
        self.config = config or {}

    def load_artifacts(self, strategy_name: str) -> dict[str, Any]:
        """Load the latest research artifacts for a strategy.

        Args:
            strategy_name: Name of the strategy.

        Returns:
            Dict containing manifest, backtest, diagnostics, and review data.
        """
        run_dir = self._find_latest_run_dir(strategy_name)
        if run_dir is None:
            raise FileNotFoundError(f"No research run found for strategy: {strategy_name}")

        artifacts = {}

        manifest_path = run_dir / "manifest.json"
        if manifest_path.exists():
            artifacts["manifest"] = json.loads(manifest_path.read_text())

        backtest_path = run_dir / "backtest.json"
        if backtest_path.exists():
            artifacts["backtest"] = json.loads(backtest_path.read_text())

        diagnostics_path = run_dir / "diagnostics.json"
        if diagnostics_path.exists():
            artifacts["diagnostics"] = json.loads(diagnostics_path.read_text())

        review_path = run_dir / "review.json"
        if review_path.exists():
            artifacts["review"] = json.loads(review_path.read_text())

        config_path = run_dir / "config.json"
        if config_path.exists():
            artifacts["config"] = json.loads(config_path.read_text())

        artifacts["run_dir"] = str(run_dir)
        return artifacts

    def _find_latest_run_dir(self, strategy_name: str) -> Path | None:
        """Find the latest run directory for a strategy."""
        if not self.artifact_directory.exists():
            return None

        strategy_underscore = strategy_name.replace("-", "_")
        strategy_dash = strategy_name.replace("_", "-")

        run_dirs = []
        for item in self.artifact_directory.iterdir():
            if item.is_dir():
                name_lower = item.name.lower()
                if strategy_underscore in name_lower or strategy_dash in name_lower:
                    run_dirs.append(item)

        if not run_dirs:
            return None

        run_dirs.sort(key=lambda x: x.name, reverse=True)
        return run_dirs[0]

    def analyze(self, strategy_name: str) -> OptimizationProposal:
        """Analyze strategy artifacts and produce an optimization proposal.

        Args:
            strategy_name: Name of the strategy to optimize.

        Returns:
            OptimizationProposal with status and parameter changes.
        """
        artifacts = self.load_artifacts(strategy_name)
        run_dir = artifacts.get("run_dir", "")

        review = artifacts.get("review", {})
        review_status = review.get("status", "")

        if review_status == "REJECTED":
            return OptimizationProposal(
                strategy_name=strategy_name,
                status=self.STATUS_REJECTED,
                rationale="Strategy was rejected in last review. No proposals until strategy is re-approved.",
                based_on_artifacts=[f"{run_dir}/review.json"],
            )

        diagnostics = artifacts.get("diagnostics", {})
        summary = diagnostics.get("summary", {})

        sharpe_ratio = summary.get("sharpe_ratio", 0.0)
        max_drawdown = abs(summary.get("max_drawdown", 0.0))

        trade_count = summary.get("trade_count", 0)
        win_rate = self._calculate_win_rate(artifacts)

        if trade_count < 10:
            return OptimizationProposal(
                strategy_name=strategy_name,
                status=self.STATUS_NEEDS_MORE_RESEARCH,
                rationale=f"Insufficient trades ({trade_count}) for optimization. Need more research data.",
                based_on_artifacts=[f"{run_dir}/diagnostics.json"],
            )

        if sharpe_ratio < self.DIAGNOSTIC_THRESHOLDS["min_sharpe_ratio"]:
            return OptimizationProposal(
                strategy_name=strategy_name,
                status=self.STATUS_NEEDS_MORE_RESEARCH,
                rationale=f"Sharpe ratio ({sharpe_ratio:.2f}) below threshold ({self.DIAGNOSTIC_THRESHOLDS['min_sharpe_ratio']}). Needs more research.",
                based_on_artifacts=[f"{run_dir}/diagnostics.json"],
            )

        if max_drawdown > self.DIAGNOSTIC_THRESHOLDS["max_drawdown"]:
            return OptimizationProposal(
                strategy_name=strategy_name,
                status=self.STATUS_NEEDS_MORE_RESEARCH,
                rationale=f"Max drawdown ({max_drawdown:.2%}) exceeds threshold ({self.DIAGNOSTIC_THRESHOLDS['max_drawdown']:.2%}). Needs more research.",
                based_on_artifacts=[f"{run_dir}/diagnostics.json"],
            )

        if win_rate < self.DIAGNOSTIC_THRESHOLDS["min_win_rate"]:
            return OptimizationProposal(
                strategy_name=strategy_name,
                status=self.STATUS_NEEDS_MORE_RESEARCH,
                rationale=f"Win rate ({win_rate:.2%}) below threshold ({self.DIAGNOSTIC_THRESHOLDS['min_win_rate']:.2%}). Needs more research.",
                based_on_artifacts=[f"{run_dir}/diagnostics.json"],
            )

        parameter_changes = self._propose_parameter_changes(artifacts)

        return OptimizationProposal(
            strategy_name=strategy_name,
            status=self.STATUS_PROPOSED_FOR_REVIEW,
            parameter_changes=parameter_changes,
            rationale="Based on historical walk-forward diagnostics, parameter adjustments are proposed for further research validation. No profitability is claimed.",
            based_on_artifacts=[
                f"{run_dir}/diagnostics.json",
                f"{run_dir}/config.json",
            ],
        )

    def _calculate_win_rate(self, artifacts: dict[str, Any]) -> float:
        """Calculate win rate from review or backtest data."""
        review = artifacts.get("review", {})
        metrics = review.get("metrics", {})
        return metrics.get("win_rate", 0.0)

    def _propose_parameter_changes(self, artifacts: dict[str, Any]) -> dict[str, Any]:
        """Propose deterministic parameter changes based on diagnostics."""
        config = artifacts.get("config", {})
        diagnostics = artifacts.get("diagnostics", {})
        summary = diagnostics.get("summary", {})

        changes = {}

        trade_count = summary.get("trade_count", 0)
        sharpe_ratio = summary.get("sharpe_ratio", 0.0)

        if trade_count > 0 and trade_count < 30:
            if "min_return" in str(config):
                changes["entry_min_return"] = "Increase threshold by 5% to reduce trade frequency"
        elif sharpe_ratio > 0.5:
            changes["position_size"] = "Consider slight increase (5%) given strong risk-adjusted returns"

        if "symbols" in config:
            symbols = config.get("symbols", [])
            if len(symbols) > 3:
                changes["universe"] = "Consider adding 1-2 more symbols for diversification"

        if not changes:
            changes["general"] = "Minor tuning (5% parameter adjustment) recommended"

        return changes

    def write_proposal(self, proposal: OptimizationProposal, output_dir: str) -> Path:
        """Write optimization proposal to JSON file.

        Args:
            proposal: The optimization proposal to write.
            output_dir: Directory to write the proposal.

        Returns:
            Path to the written file.
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        file_path = output_path / "optimization_proposal.json"
        with file_path.open("w", encoding="utf-8") as f:
            json.dump(proposal.to_dict(), f, indent=2, sort_keys=True)

        return file_path