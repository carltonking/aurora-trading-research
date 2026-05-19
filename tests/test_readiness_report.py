"""Tests for readiness report generator."""

import json
import tempfile
from pathlib import Path

import pytest

from aurora.analysis.paper_performance import PaperMetrics
from aurora.optimization.adaptive_optimizer import OptimizationProposal
from aurora.reporting.readiness_report import ReadinessReport, ReadinessReportGenerator


def create_research_run(base_path: Path, strategy_name: str, backtest: dict, diagnostics: dict, review: dict) -> Path:
    """Create a mock research run directory with artifacts."""
    run_dir = base_path / f"20260519T000000Z_{strategy_name}"
    run_dir.mkdir(parents=True, exist_ok=True)

    (run_dir / "backtest.json").write_text(json.dumps(backtest))
    (run_dir / "diagnostics.json").write_text(json.dumps(diagnostics))
    (run_dir / "review.json").write_text(json.dumps(review))

    return run_dir


def test_report_generation_all_good() -> None:
    """Test report generation with all artifacts and good metrics."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)

        backtest = {
            "metrics": {
                "total_return": 0.15,
                "annualized_return": 0.12,
                "sharpe_ratio": 0.8,
                "max_drawdown": -0.1,
                "win_rate": 0.55,
                "trade_count": 50,
                "profit_factor": 1.5,
            }
        }
        diagnostics = {
            "summary": {
                "sharpe_ratio": 0.7,
                "max_drawdown": -0.12,
                "win_rate": 0.5,
                "trade_count": 45,
                "total_return": 0.12,
            }
        }
        review = {"status": "APPROVED_FOR_PAPER_SIMULATION"}

        create_research_run(base_path, "test_strategy", backtest, diagnostics, review)

        paper_metrics_path = base_path / "paper_metrics.json"
        paper_metrics_path.write_text(json.dumps({
            "strategy_name": "test_strategy",
            "total_trades": 30,
            "win_count": 12,
            "loss_count": 18,
            "win_rate": 0.4,
            "total_pnl": 500.0,
            "max_drawdown": 0.15,
            "sharpe_ratio": 0.6,
        }))

        proposal_path = base_path / "proposal.json"
        proposal_path.write_text(json.dumps({
            "strategy_name": "test_strategy",
            "status": "PROPOSED_FOR_REVIEW",
            "parameter_changes": {"position_size": "increase 5%"},
            "rationale": "Based on historical diagnostics.",
            "based_on_artifacts": [],
        }))

        generator = ReadinessReportGenerator(
            artifact_directory=str(base_path),
            strategy_name="test_strategy",
            paper_metrics_path=str(paper_metrics_path),
            proposal_path=str(proposal_path),
        )

        report = generator.generate()

        assert report.strategy_name == "test_strategy"
        assert report.backtest_summary["sharpe_ratio"] == 0.8
        assert report.paper_performance is not None
        assert report.paper_performance.win_rate == 0.4
        assert report.optimization_proposal is not None
        assert "gates passed" in report.overall_assessment.lower()


def test_report_generation_paper_weak() -> None:
    """Test report generation when paper performance is weak."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)

        backtest = {
            "metrics": {
                "total_return": 0.1,
                "sharpe_ratio": 0.6,
                "max_drawdown": -0.15,
                "win_rate": 0.45,
                "trade_count": 50,
            }
        }
        diagnostics = {
            "summary": {
                "sharpe_ratio": 0.55,
                "max_drawdown": -0.18,
                "win_rate": 0.42,
                "trade_count": 45,
            }
        }
        review = {"status": "APPROVED_FOR_PAPER_SIMULATION"}

        create_research_run(base_path, "test_strategy", backtest, diagnostics, review)

        paper_metrics_path = base_path / "paper_metrics.json"
        paper_metrics_path.write_text(json.dumps({
            "strategy_name": "test_strategy",
            "total_trades": 30,
            "win_count": 8,
            "loss_count": 22,
            "win_rate": 0.27,
            "max_drawdown": 0.5,
            "sharpe_ratio": 0.2,
        }))

        generator = ReadinessReportGenerator(
            artifact_directory=str(base_path),
            strategy_name="test_strategy",
            paper_metrics_path=str(paper_metrics_path),
        )

        report = generator.generate()

        assert "elevated risk" in report.overall_assessment.lower()


def test_report_generation_needs_more_research() -> None:
    """Test report generation when optimization proposal is NEEDS_MORE_RESEARCH."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)

        backtest = {
            "metrics": {
                "total_return": -0.05,
                "sharpe_ratio": 0.2,
                "max_drawdown": -0.25,
                "win_rate": 0.35,
                "trade_count": 50,
            }
        }
        diagnostics = {
            "summary": {
                "sharpe_ratio": 0.15,
                "max_drawdown": -0.28,
                "win_rate": 0.3,
                "trade_count": 45,
            }
        }
        review = {"status": "APPROVED_FOR_PAPER_SIMULATION"}

        create_research_run(base_path, "test_strategy", backtest, diagnostics, review)

        proposal_path = base_path / "proposal.json"
        proposal_path.write_text(json.dumps({
            "strategy_name": "test_strategy",
            "status": "NEEDS_MORE_RESEARCH",
            "parameter_changes": {},
            "rationale": "Sharpe ratio below threshold.",
            "based_on_artifacts": [],
        }))

        generator = ReadinessReportGenerator(
            artifact_directory=str(base_path),
            strategy_name="test_strategy",
            proposal_path=str(proposal_path),
        )

        report = generator.generate()

        assert "further research" in report.overall_assessment.lower()


def test_report_generation_missing_artifacts() -> None:
    """Test report generation with missing optional artifacts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)

        backtest = {
            "metrics": {
                "total_return": 0.1,
                "sharpe_ratio": 0.6,
                "max_drawdown": -0.1,
                "win_rate": 0.5,
                "trade_count": 50,
            }
        }
        diagnostics = {
            "summary": {
                "sharpe_ratio": 0.55,
                "max_drawdown": -0.12,
                "win_rate": 0.48,
                "trade_count": 45,
            }
        }
        review = {"status": "APPROVED_FOR_PAPER_SIMULATION"}

        create_research_run(base_path, "test_strategy", backtest, diagnostics, review)

        generator = ReadinessReportGenerator(
            artifact_directory=str(base_path),
            strategy_name="test_strategy",
        )

        report = generator.generate()

        assert report.strategy_name == "test_strategy"
        assert report.paper_performance is None
        assert report.optimization_proposal is None
        assert "gates passed" in report.overall_assessment.lower()


def test_report_json_output() -> None:
    """Test that JSON output contains required fields."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)

        backtest = {
            "metrics": {
                "total_return": 0.1,
                "sharpe_ratio": 0.6,
                "max_drawdown": -0.1,
                "win_rate": 0.5,
                "trade_count": 50,
            }
        }
        diagnostics = {
            "summary": {
                "sharpe_ratio": 0.55,
                "max_drawdown": -0.12,
                "win_rate": 0.48,
                "trade_count": 45,
            }
        }
        review = {"status": "APPROVED_FOR_PAPER_SIMULATION"}

        create_research_run(base_path, "test_strategy", backtest, diagnostics, review)

        generator = ReadinessReportGenerator(
            artifact_directory=str(base_path),
            strategy_name="test_strategy",
        )

        report = generator.generate()
        report_dict = report.to_dict()

        assert "strategy_name" in report_dict
        assert "generated_at" in report_dict
        assert "disclaimer" in report_dict
        assert "research purposes only" in report_dict["disclaimer"]
        assert "does not guarantee" in report_dict["disclaimer"]


def test_report_save() -> None:
    """Test saving report to file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)

        backtest = {
            "metrics": {
                "total_return": 0.1,
                "sharpe_ratio": 0.6,
                "max_drawdown": -0.1,
                "win_rate": 0.5,
                "trade_count": 50,
            }
        }
        diagnostics = {
            "summary": {
                "sharpe_ratio": 0.55,
                "max_drawdown": -0.12,
                "win_rate": 0.48,
                "trade_count": 45,
            }
        }
        review = {"status": "APPROVED_FOR_PAPER_SIMULATION"}

        create_research_run(base_path, "test_strategy", backtest, diagnostics, review)

        generator = ReadinessReportGenerator(
            artifact_directory=str(base_path),
            strategy_name="test_strategy",
        )

        report = generator.generate()
        output_path = base_path / "report.json"
        saved_path = generator.save_report(report, str(output_path))

        assert saved_path.exists()

        with saved_path.open() as f:
            loaded = json.load(f)
        assert loaded["strategy_name"] == "test_strategy"
        assert "disclaimer" in loaded


def test_mixed_signals_assessment() -> None:
    """Test assessment when metrics are mixed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)

        backtest = {
            "metrics": {
                "total_return": 0.1,
                "sharpe_ratio": 0.3,
                "max_drawdown": -0.25,
                "win_rate": 0.35,
                "trade_count": 50,
            }
        }
        diagnostics = {
            "summary": {
                "sharpe_ratio": 0.25,
                "max_drawdown": -0.28,
                "win_rate": 0.32,
                "trade_count": 45,
            }
        }
        review = {"status": "APPROVED_FOR_PAPER_SIMULATION"}

        create_research_run(base_path, "test_strategy", backtest, diagnostics, review)

        generator = ReadinessReportGenerator(
            artifact_directory=str(base_path),
            strategy_name="test_strategy",
        )

        report = generator.generate()

        assert "mixed signals" in report.overall_assessment.lower()