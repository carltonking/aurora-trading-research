import json
import tempfile
from pathlib import Path

import pytest

from aurora.optimization.adaptive_optimizer import AdaptiveOptimizer, OptimizationProposal


def create_artifact_dir(base_path: Path, strategy_name: str, review_status: str, diagnostics: dict) -> Path:
    """Create a test artifact directory with sample files."""
    run_dir = base_path / f"20260519T120000Z_{strategy_name}"
    run_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "strategy_id": strategy_name,
        "run_id": f"20260519T120000Z_{strategy_name}",
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest))

    backtest = {
        "metrics": {
            "sharpe_ratio": diagnostics.get("sharpe_ratio", 0.5),
            "max_drawdown": diagnostics.get("max_drawdown", 0.1),
            "trade_count": diagnostics.get("trade_count", 50),
        }
    }
    (run_dir / "backtest.json").write_text(json.dumps(backtest))

    diags = {
        "summary": diagnostics,
    }
    (run_dir / "diagnostics.json").write_text(json.dumps(diags))

    review = {
        "status": review_status,
        "metrics": {
            "sharpe_ratio": diagnostics.get("sharpe_ratio", 0.5),
            "max_drawdown": diagnostics.get("max_drawdown", 0.1),
            "win_rate": diagnostics.get("win_rate", 0.5),
            "trade_count": diagnostics.get("trade_count", 50),
        },
    }
    (run_dir / "review.json").write_text(json.dumps(review))

    config = {
        "strategy_id": strategy_name,
        "symbols": ["SPY", "QQQ"],
    }
    (run_dir / "config.json").write_text(json.dumps(config))

    return run_dir


def test_proposal_rejected_when_review_rejected() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)
        create_artifact_dir(base_path, "test_strategy", "REJECTED", {})

        optimizer = AdaptiveOptimizer(artifact_directory=str(base_path))
        proposal = optimizer.analyze("test_strategy")

        assert proposal.status == "REJECTED"
        assert "rejected" in proposal.rationale.lower()


def test_proposal_needs_more_research_when_low_sharpe() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)
        create_artifact_dir(
            base_path,
            "test_strategy",
            "APPROVED_FOR_PAPER_SIMULATION",
            {"sharpe_ratio": 0.2, "max_drawdown": 0.1, "trade_count": 50, "win_rate": 0.5},
        )

        optimizer = AdaptiveOptimizer(artifact_directory=str(base_path))
        proposal = optimizer.analyze("test_strategy")

        assert proposal.status == "NEEDS_MORE_RESEARCH"
        assert "Sharpe" in proposal.rationale


def test_proposal_needs_more_research_when_high_drawdown() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)
        create_artifact_dir(
            base_path,
            "test_strategy",
            "APPROVED_FOR_PAPER_SIMULATION",
            {"sharpe_ratio": 0.8, "max_drawdown": 0.5, "trade_count": 50, "win_rate": 0.5},
        )

        optimizer = AdaptiveOptimizer(artifact_directory=str(base_path))
        proposal = optimizer.analyze("test_strategy")

        assert proposal.status == "NEEDS_MORE_RESEARCH"
        assert "drawdown" in proposal.rationale.lower()


def test_proposal_proposed_for_review_when_acceptable() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)
        create_artifact_dir(
            base_path,
            "test_strategy",
            "APPROVED_FOR_PAPER_SIMULATION",
            {"sharpe_ratio": 0.8, "max_drawdown": 0.1, "trade_count": 50, "win_rate": 0.5},
        )

        optimizer = AdaptiveOptimizer(artifact_directory=str(base_path))
        proposal = optimizer.analyze("test_strategy")

        assert proposal.status == "PROPOSED_FOR_REVIEW"
        assert len(proposal.parameter_changes) > 0
        assert "Based on historical walk-forward diagnostics" in proposal.rationale


def test_proposal_needs_more_research_when_low_trade_count() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)
        create_artifact_dir(
            base_path,
            "test_strategy",
            "APPROVED_FOR_PAPER_SIMULATION",
            {"sharpe_ratio": 0.8, "max_drawdown": 0.1, "trade_count": 5, "win_rate": 0.5},
        )

        optimizer = AdaptiveOptimizer(artifact_directory=str(base_path))
        proposal = optimizer.analyze("test_strategy")

        assert proposal.status == "NEEDS_MORE_RESEARCH"
        assert "Insufficient trades" in proposal.rationale


def test_proposal_write_to_file() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)
        create_artifact_dir(
            base_path,
            "test_strategy",
            "APPROVED_FOR_PAPER_SIMULATION",
            {"sharpe_ratio": 0.8, "max_drawdown": 0.1, "trade_count": 50, "win_rate": 0.5},
        )

        optimizer = AdaptiveOptimizer(artifact_directory=str(base_path))
        proposal = optimizer.analyze("test_strategy")

        output_dir = Path(tmpdir) / "output"
        output_path = optimizer.write_proposal(proposal, str(output_dir))

        assert output_path.exists()
        with output_path.open() as f:
            written = json.load(f)
        assert written["strategy_name"] == "test_strategy"
        assert written["status"] == "PROPOSED_FOR_REVIEW"


def test_proposal_to_dict_contains_no_secrets() -> None:
    proposal = OptimizationProposal(
        strategy_name="test_strategy",
        status="PROPOSED_FOR_REVIEW",
        parameter_changes={"param": "value"},
        rationale="Test rationale",
        based_on_artifacts=["path1", "path2"],
    )

    result = proposal.to_dict()

    assert "test_strategy" in str(result)
    assert "PROPOSED_FOR_REVIEW" in str(result)
    assert "value" in str(result)


def test_load_artifacts_raises_when_no_run_found() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        optimizer = AdaptiveOptimizer(artifact_directory=tmpdir)
        with pytest.raises(FileNotFoundError):
            optimizer.load_artifacts("nonexistent_strategy")


def test_optimizer_version_set() -> None:
    proposal = OptimizationProposal(
        strategy_name="test",
        status="PROPOSED_FOR_REVIEW",
    )
    assert proposal.optimizer_version == "3.0.0"


def create_paper_metrics_file(base_path: Path, metrics: dict) -> Path:
    """Create a paper metrics JSON file."""
    metrics_path = base_path / "paper_metrics.json"
    metrics_path.write_text(json.dumps(metrics))
    return metrics_path


def test_paper_metrics_weak_win_rate_returns_needs_more_research() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)
        create_artifact_dir(
            base_path,
            "test_strategy",
            "APPROVED_FOR_PAPER_SIMULATION",
            {"sharpe_ratio": 0.8, "max_drawdown": 0.1, "trade_count": 50, "win_rate": 0.5},
        )

        paper_metrics_path = create_paper_metrics_file(
            base_path,
            {
                "strategy_name": "test_strategy",
                "win_rate": 0.25,
                "max_drawdown": 0.1,
                "sharpe_ratio": 0.5,
            },
        )

        optimizer = AdaptiveOptimizer(
            artifact_directory=str(base_path),
            paper_metrics_path=str(paper_metrics_path),
        )
        proposal = optimizer.analyze("test_strategy")

        assert proposal.status == "NEEDS_MORE_RESEARCH"
        assert "win rate" in proposal.rationale.lower()
        assert "paper" in proposal.rationale.lower()


def test_paper_metrics_weak_drawdown_returns_needs_more_research() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)
        create_artifact_dir(
            base_path,
            "test_strategy",
            "APPROVED_FOR_PAPER_SIMULATION",
            {"sharpe_ratio": 0.8, "max_drawdown": 0.1, "trade_count": 50, "win_rate": 0.5},
        )

        paper_metrics_path = create_paper_metrics_file(
            base_path,
            {
                "strategy_name": "test_strategy",
                "win_rate": 0.5,
                "max_drawdown": 0.6,
                "sharpe_ratio": 0.3,
            },
        )

        optimizer = AdaptiveOptimizer(
            artifact_directory=str(base_path),
            paper_metrics_path=str(paper_metrics_path),
        )
        proposal = optimizer.analyze("test_strategy")

        assert proposal.status == "NEEDS_MORE_RESEARCH"
        assert "drawdown" in proposal.rationale.lower()
        assert "paper" in proposal.rationale.lower()


def test_paper_metrics_declining_performance_proposes_conservative_changes() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)
        create_artifact_dir(
            base_path,
            "test_strategy",
            "APPROVED_FOR_PAPER_SIMULATION",
            {"sharpe_ratio": 1.0, "max_drawdown": 0.1, "trade_count": 50, "win_rate": 0.5},
        )

        paper_metrics_path = create_paper_metrics_file(
            base_path,
            {
                "strategy_name": "test_strategy",
                "win_rate": 0.5,
                "max_drawdown": 0.2,
                "sharpe_ratio": 0.3,
            },
        )

        optimizer = AdaptiveOptimizer(
            artifact_directory=str(base_path),
            paper_metrics_path=str(paper_metrics_path),
        )
        proposal = optimizer.analyze("test_strategy")

        assert proposal.status == "PROPOSED_FOR_REVIEW"
        assert "paper performance lagging" in proposal.rationale.lower()
        assert any("position" in k.lower() for k in proposal.parameter_changes.keys())


def test_paper_metrics_in_line_returns_proposed_for_review() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)
        create_artifact_dir(
            base_path,
            "test_strategy",
            "APPROVED_FOR_PAPER_SIMULATION",
            {"sharpe_ratio": 0.8, "max_drawdown": 0.1, "trade_count": 50, "win_rate": 0.5},
        )

        paper_metrics_path = create_paper_metrics_file(
            base_path,
            {
                "strategy_name": "test_strategy",
                "win_rate": 0.5,
                "max_drawdown": 0.1,
                "sharpe_ratio": 0.7,
            },
        )

        optimizer = AdaptiveOptimizer(
            artifact_directory=str(base_path),
            paper_metrics_path=str(paper_metrics_path),
        )
        proposal = optimizer.analyze("test_strategy")

        assert proposal.status == "PROPOSED_FOR_REVIEW"
        assert "paper trading results indicate alignment" in proposal.rationale.lower()
        assert any(str(paper_metrics_path) in a for a in proposal.based_on_artifacts)


def test_no_paper_metrics_path_returns_old_behavior() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)
        create_artifact_dir(
            base_path,
            "test_strategy",
            "APPROVED_FOR_PAPER_SIMULATION",
            {"sharpe_ratio": 0.8, "max_drawdown": 0.1, "trade_count": 50, "win_rate": 0.5},
        )

        optimizer = AdaptiveOptimizer(
            artifact_directory=str(base_path),
            paper_metrics_path=None,
        )
        proposal = optimizer.analyze("test_strategy")

        assert proposal.status == "PROPOSED_FOR_REVIEW"
        assert "Based on historical walk-forward diagnostics" in proposal.rationale
        assert len([a for a in proposal.based_on_artifacts if "paper" in a.lower()]) == 0


def test_nonexistent_paper_metrics_path_returns_old_behavior() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)
        create_artifact_dir(
            base_path,
            "test_strategy",
            "APPROVED_FOR_PAPER_SIMULATION",
            {"sharpe_ratio": 0.8, "max_drawdown": 0.1, "trade_count": 50, "win_rate": 0.5},
        )

        optimizer = AdaptiveOptimizer(
            artifact_directory=str(base_path),
            paper_metrics_path="nonexistent/path.json",
        )
        proposal = optimizer.analyze("test_strategy")

        assert proposal.status == "PROPOSED_FOR_REVIEW"
        assert "Based on historical walk-forward diagnostics" in proposal.rationale