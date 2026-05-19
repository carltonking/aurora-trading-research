"""Readiness report - aggregates research artifacts for comprehensive strategy assessment.

This module is research-only. It aggregates backtest, walk-forward diagnostics,
paper-trading performance, and optimization proposals into a comprehensive report.
No live trading, no broker calls, no profitability claims.
"""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aurora.analysis.paper_performance import PaperMetrics
from aurora.optimization.adaptive_optimizer import OptimizationProposal


@dataclass
class ReadinessReport:
    """Comprehensive readiness report for a strategy."""

    strategy_name: str
    generated_at: str
    backtest_summary: dict[str, Any] = field(default_factory=dict)
    walk_forward_summary: dict[str, Any] = field(default_factory=dict)
    paper_performance: PaperMetrics | None = None
    optimization_proposal: OptimizationProposal | None = None
    overall_assessment: str = ""
    disclaimer: str = ""
    sections: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary for JSON serialization."""
        result = {
            "strategy_name": self.strategy_name,
            "generated_at": self.generated_at,
            "backtest_summary": self.backtest_summary,
            "walk_forward_summary": self.walk_forward_summary,
            "paper_performance": self.paper_performance.to_dict() if self.paper_performance else None,
            "optimization_proposal": self.optimization_proposal.to_dict() if self.optimization_proposal else None,
            "overall_assessment": self.overall_assessment,
            "disclaimer": self.disclaimer,
            "sections": self.sections,
        }
        return result


class ReadinessReportGenerator:
    """Generate comprehensive readiness reports from research artifacts.

    This is a research-only generator. It aggregates research artifacts and
    produces a comprehensive assessment. No live trading, no broker calls.
    """

    METRIC_THRESHOLDS = {
        "min_sharpe_ratio": 0.5,
        "max_drawdown": 0.3,
        "min_win_rate": 0.4,
        "paper_min_win_rate": 0.35,
        "paper_max_drawdown": 0.4,
    }

    DEFAULT_DISCLAIMER = (
        "This report is for research purposes only. Past performance—historical or paper—does not guarantee future results. "
        "AURORA does not provide financial advice. Any decision to deploy this strategy is entirely the user's responsibility."
    )

    def __init__(
        self,
        artifact_directory: str,
        strategy_name: str,
        paper_metrics_path: str | None = None,
        proposal_path: str | None = None,
    ) -> None:
        """Initialize report generator.

        Args:
            artifact_directory: Directory containing research run artifacts.
            strategy_name: Name of the strategy to generate report for.
            paper_metrics_path: Optional path to paper performance metrics.
            proposal_path: Optional path to optimization proposal.
        """
        self.artifact_directory = Path(artifact_directory)
        self.strategy_name = strategy_name
        self.paper_metrics_path = paper_metrics_path
        self.proposal_path = proposal_path

    def load_artifacts(self) -> dict[str, Any]:
        """Load latest research artifacts for the strategy.

        Returns:
            Dict containing backtest, diagnostics, paper metrics, and proposal data.
        """
        artifacts = {
            "backtest": None,
            "diagnostics": None,
            "review": None,
            "paper_metrics": None,
            "proposal": None,
        }

        run_dir = self._find_latest_run_dir()
        if run_dir:
            backtest_path = run_dir / "backtest.json"
            if backtest_path.exists():
                artifacts["backtest"] = json.loads(backtest_path.read_text())

            diagnostics_path = run_dir / "diagnostics.json"
            if diagnostics_path.exists():
                artifacts["diagnostics"] = json.loads(diagnostics_path.read_text())

            review_path = run_dir / "review.json"
            if review_path.exists():
                artifacts["review"] = json.loads(review_path.read_text())

        if self.paper_metrics_path:
            paper_path = Path(self.paper_metrics_path)
            if paper_path.exists():
                try:
                    data = json.loads(paper_path.read_text())
                    artifacts["paper_metrics"] = data
                except (json.JSONDecodeError, OSError):
                    pass

        if self.proposal_path:
            proposal_file = Path(self.proposal_path)
            if proposal_file.exists():
                try:
                    data = json.loads(proposal_file.read_text())
                    artifacts["proposal"] = data
                except (json.JSONDecodeError, OSError):
                    pass

        return artifacts

    def _find_latest_run_dir(self) -> Path | None:
        """Find the latest run directory for the strategy."""
        if not self.artifact_directory.exists():
            return None

        strategy_underscore = self.strategy_name.replace("-", "_")
        strategy_dash = self.strategy_name.replace("_", "-")

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

    def generate(self) -> ReadinessReport:
        """Generate comprehensive readiness report.

        Returns:
            ReadinessReport with aggregated metrics and assessment.
        """
        artifacts = self.load_artifacts()

        backtest = artifacts.get("backtest")
        diagnostics = artifacts.get("diagnostics")
        paper_data = artifacts.get("paper_metrics")
        proposal_data = artifacts.get("proposal")

        backtest_summary = self._extract_backtest_summary(backtest)
        walk_forward_summary = self._extract_diagnostics_summary(diagnostics)

        paper_metrics = None
        if paper_data:
            paper_metrics = PaperMetrics(
                strategy_name=paper_data.get("strategy_name", ""),
                start_date=paper_data.get("start_date"),
                end_date=paper_data.get("end_date"),
                total_trades=paper_data.get("total_trades", 0),
                win_count=paper_data.get("win_count", 0),
                loss_count=paper_data.get("loss_count", 0),
                win_rate=paper_data.get("win_rate", 0.0),
                total_pnl=paper_data.get("total_pnl", 0.0),
                avg_pnl_per_trade=paper_data.get("avg_pnl_per_trade", 0.0),
                max_drawdown=paper_data.get("max_drawdown", 0.0),
                sharpe_ratio=paper_data.get("sharpe_ratio", 0.0),
                profit_factor=paper_data.get("profit_factor", 0.0),
                avg_slippage=paper_data.get("avg_slippage", 0.0),
                timestamp=paper_data.get("timestamp", ""),
            )

        optimization_proposal = None
        if proposal_data:
            optimization_proposal = OptimizationProposal(
                strategy_name=proposal_data.get("strategy_name", ""),
                status=proposal_data.get("status", ""),
                parameter_changes=proposal_data.get("parameter_changes", {}),
                rationale=proposal_data.get("rationale", ""),
                based_on_artifacts=proposal_data.get("based_on_artifacts", []),
                timestamp=proposal_data.get("timestamp", ""),
                optimizer_version=proposal_data.get("optimizer_version", ""),
            )

        overall_assessment = self._compute_assessment(
            backtest_summary, walk_forward_summary, paper_metrics, optimization_proposal
        )

        sections = self._build_sections(backtest_summary, walk_forward_summary, paper_metrics, optimization_proposal)

        return ReadinessReport(
            strategy_name=self.strategy_name,
            generated_at=datetime.now(UTC).isoformat(),
            backtest_summary=backtest_summary,
            walk_forward_summary=walk_forward_summary,
            paper_performance=paper_metrics,
            optimization_proposal=optimization_proposal,
            overall_assessment=overall_assessment,
            disclaimer=self.DEFAULT_DISCLAIMER,
            sections=sections,
        )

    def _extract_backtest_summary(self, backtest: dict | None) -> dict[str, Any]:
        """Extract key metrics from backtest data."""
        if not backtest:
            return {}
        metrics = backtest.get("metrics", {})
        return {
            "total_return": metrics.get("total_return"),
            "annualized_return": metrics.get("annualized_return"),
            "sharpe_ratio": metrics.get("sharpe_ratio"),
            "max_drawdown": metrics.get("max_drawdown"),
            "win_rate": metrics.get("win_rate"),
            "trade_count": metrics.get("trade_count"),
            "profit_factor": metrics.get("profit_factor"),
        }

    def _extract_diagnostics_summary(self, diagnostics: dict | None) -> dict[str, Any]:
        """Extract key metrics from diagnostics data."""
        if not diagnostics:
            return {}
        return diagnostics.get("summary", {})

    def _compute_assessment(
        self,
        backtest_summary: dict,
        walk_forward_summary: dict,
        paper_metrics: PaperMetrics | None,
        proposal: OptimizationProposal | None,
    ) -> str:
        """Compute overall assessment based on heuristics."""
        thresholds = self.METRIC_THRESHOLDS

        if paper_metrics:
            if paper_metrics.win_rate < thresholds["paper_min_win_rate"]:
                return "Exercise caution: paper trading performance shows elevated risk."
            if paper_metrics.max_drawdown > thresholds["paper_max_drawdown"]:
                return "Exercise caution: paper trading performance shows elevated risk."

        if proposal and proposal.status == "NEEDS_MORE_RESEARCH":
            return "Further research recommended before considering deployment."

        sharpe = backtest_summary.get("sharpe_ratio", 0) or walk_forward_summary.get("sharpe_ratio", 0)
        max_dd = abs(backtest_summary.get("max_drawdown", 0) or walk_forward_summary.get("max_drawdown", 0))
        win_rate = backtest_summary.get("win_rate", 0) or walk_forward_summary.get("win_rate", 0)

        if sharpe and sharpe >= thresholds["min_sharpe_ratio"]:
            if max_dd <= thresholds["max_drawdown"]:
                if win_rate and win_rate >= thresholds["min_win_rate"]:
                    return "All research gates passed. The strategy shows acceptable historical and paper-trading characteristics. No guarantee of future performance."

        if sharpe or max_dd or win_rate:
            return "Mixed signals. Additional validation suggested."

        return "Insufficient data for assessment."

    def _build_sections(
        self,
        backtest_summary: dict,
        walk_forward_summary: dict,
        paper_metrics: PaperMetrics | None,
        proposal: OptimizationProposal | None,
    ) -> list[dict[str, Any]]:
        """Build structured sections for the report."""
        sections = []

        if backtest_summary:
            sections.append({
                "title": "Backtest Performance",
                "content": backtest_summary,
            })

        if walk_forward_summary:
            sections.append({
                "title": "Walk-Forward Diagnostics",
                "content": walk_forward_summary,
            })

        if paper_metrics:
            sections.append({
                "title": "Paper Trading Performance",
                "content": paper_metrics.to_dict(),
            })

        if proposal:
            sections.append({
                "title": "Optimization Proposal",
                "content": {
                    "status": proposal.status,
                    "rationale": proposal.rationale,
                    "parameter_changes": proposal.parameter_changes,
                },
            })

        return sections

    def save_report(self, report: ReadinessReport, output_path: str) -> Path:
        """Save report as JSON and print markdown summary.

        Args:
            report: The readiness report to save.
            output_path: Path to save the JSON report.

        Returns:
            Path to the saved JSON file.
        """
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with output_file.open("w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, indent=2, sort_keys=False)

        self._print_markdown_summary(report)

        return output_file

    def _print_markdown_summary(self, report: ReadinessReport) -> None:
        """Print markdown summary to stdout."""
        print("\n" + "=" * 60)
        print(f"READINESS REPORT: {report.strategy_name}")
        print("=" * 60)

        print(f"\nGenerated: {report.generated_at}")

        print("\n## Backtest Summary")
        for key, value in report.backtest_summary.items():
            if value is not None:
                if isinstance(value, float):
                    print(f"  {key}: {value:.4f}")
                else:
                    print(f"  {key}: {value}")

        print("\n## Walk-Forward Summary")
        for key, value in report.walk_forward_summary.items():
            if value is not None:
                if isinstance(value, float):
                    print(f"  {key}: {value:.4f}")
                else:
                    print(f"  {key}: {value}")

        if report.paper_performance:
            print("\n## Paper Trading Performance")
            pm = report.paper_performance
            print(f"  Total Trades: {pm.total_trades}")
            print(f"  Win Rate: {pm.win_rate:.2%}")
            print(f"  Total P&L: ${pm.total_pnl:.2f}")
            print(f"  Max Drawdown: {pm.max_drawdown:.2%}")
            print(f"  Sharpe Ratio: {pm.sharpe_ratio:.3f}")

        if report.optimization_proposal:
            print("\n## Optimization Proposal")
            op = report.optimization_proposal
            print(f"  Status: {op.status}")
            print(f"  Rationale: {op.rationale[:100]}...")
            if op.parameter_changes:
                print("  Parameter Changes:")
                for key, value in op.parameter_changes.items():
                    print(f"    - {key}: {value}")

        print("\n## Overall Assessment")
        print(f"  {report.overall_assessment}")

        print("\n## Disclaimer")
        print(f"  {report.disclaimer}")

        print("\n" + "=" * 60)