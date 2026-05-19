"""Tests for strategy exporter."""

import json
import tempfile
from pathlib import Path

import pytest

from aurora.export.strategy_exporter import ExportBundle, SecretDetectionError, StrategyExporter


def test_export_bundle_creation() -> None:
    """Test creating an export bundle."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)

        strategy_file = base_path / "my_strategy.py"
        strategy_file.write_text("""
class MyStrategy:
    def __init__(self):
        self.name = "test"
""")

        model_file = base_path / "model.pkl"
        model_file.write_text("dummy model data")

        feature_config = base_path / "feature_config.json"
        feature_config.write_text(json.dumps({"features": ["a", "b", "c"]}))

        readiness = base_path / "readiness_report.json"
        readiness.write_text(json.dumps({
            "strategy_name": "test_strategy",
            "overall_assessment": "All gates passed"
        }))

        output_zip = base_path / "bundle.zip"

        exporter = StrategyExporter(
            strategy_name="test_strategy",
            artifact_directory=str(base_path),
            output_zip_path=str(output_zip),
            strategy_file_path=str(strategy_file),
            model_path=str(model_file),
            feature_config_path=str(feature_config),
            readiness_report_path=str(readiness),
        )

        bundle = exporter.create_bundle()

        assert bundle.strategy_name == "test_strategy"
        assert "strategy.py" in bundle.files
        assert "model.pkl" in bundle.files
        assert "feature_config.json" in bundle.files
        assert "readiness_report.json" in bundle.files
        assert output_zip.exists()


def test_export_missing_optional_files() -> None:
    """Test export with missing optional files (should warn, not fail)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)

        strategy_file = base_path / "my_strategy.py"
        strategy_file.write_text("class MyStrategy: pass")

        output_zip = base_path / "bundle.zip"

        exporter = StrategyExporter(
            strategy_name="test_strategy",
            artifact_directory=str(base_path),
            output_zip_path=str(output_zip),
            strategy_file_path=str(strategy_file),
        )

        bundle = exporter.create_bundle()

        assert bundle.strategy_name == "test_strategy"
        assert "strategy.py" in bundle.files
        assert output_zip.exists()


def test_verify_valid_bundle() -> None:
    """Test bundle verification with valid bundle."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)

        strategy_file = base_path / "strategy.py"
        strategy_file.write_text("class Strategy: pass")

        output_zip = base_path / "bundle.zip"

        exporter = StrategyExporter(
            strategy_name="test",
            artifact_directory=str(base_path),
            output_zip_path=str(output_zip),
            strategy_file_path=str(strategy_file),
        )

        exporter.create_bundle()

        assert exporter.verify_bundle() is True


def test_verify_invalid_bundle() -> None:
    """Test bundle verification with invalid/missing bundle."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)

        exporter = StrategyExporter(
            strategy_name="test",
            artifact_directory=str(base_path),
            output_zip_path=str(base_path / "nonexistent.zip"),
        )

        assert exporter.verify_bundle() is False


def test_secret_detection_in_strategy_file() -> None:
    """Test that secrets in strategy file raise error."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)

        strategy_file = base_path / "strategy.py"
        strategy_file.write_text("""
API_KEY = "sk-1234567890abcdefghijklmnop"
""")

        output_zip = base_path / "bundle.zip"

        exporter = StrategyExporter(
            strategy_name="test",
            artifact_directory=str(base_path),
            output_zip_path=str(output_zip),
            strategy_file_path=str(strategy_file),
        )

        with pytest.raises(SecretDetectionError, match="Potential secret detected"):
            exporter.create_bundle()


def test_environment_variable_placeholder_allowed() -> None:
    """Test that environment variable placeholders are allowed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)

        strategy_file = base_path / "strategy.py"
        strategy_file.write_text("""
import os
API_KEY = os.getenv("MY_API_KEY")
SECRET = os.environ.get("MY_SECRET")
""")

        output_zip = base_path / "bundle.zip"

        exporter = StrategyExporter(
            strategy_name="test",
            artifact_directory=str(base_path),
            output_zip_path=str(output_zip),
            strategy_file_path=str(strategy_file),
        )

        bundle = exporter.create_bundle()

        assert bundle.strategy_name == "test"
        assert "strategy.py" in bundle.files


def test_manifest_includes_disclaimer() -> None:
    """Test that manifest includes required disclaimer."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)

        strategy_file = base_path / "strategy.py"
        strategy_file.write_text("class Strategy: pass")

        output_zip = base_path / "bundle.zip"

        exporter = StrategyExporter(
            strategy_name="test",
            artifact_directory=str(base_path),
            output_zip_path=str(output_zip),
            strategy_file_path=str(strategy_file),
        )

        bundle = exporter.create_bundle()

        assert "does not guarantee" in bundle.disclaimer
        assert "AURORA does not provide financial advice" in bundle.disclaimer
        assert bundle.manifest["aurora_version"]


def test_export_includes_optional_backtest_from_run_dir() -> None:
    """Test that optional backtest from run directory is included when provided."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)

        strategy_file = base_path / "test_strategy.py"
        strategy_file.write_text("class TestStrategy: pass")

        run_dir = base_path / "20260520T000000Z_test_strategy"
        run_dir.mkdir(parents=True)
        backtest_file = run_dir / "backtest.json"
        backtest_file.write_text(json.dumps({"metrics": {"total_return": 0.2}}))

        output_zip = base_path / "bundle.zip"

        exporter = StrategyExporter(
            strategy_name="test_strategy",
            artifact_directory=str(base_path),
            output_zip_path=str(output_zip),
            strategy_file_path=str(strategy_file),
        )

        bundle = exporter.create_bundle()

        assert "strategy.py" in bundle.files
        assert output_zip.exists()


def test_no_strategy_file_creates_partial_bundle() -> None:
    """Test that missing strategy file can still create partial bundle."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)

        readiness = base_path / "readiness_report.json"
        readiness.write_text(json.dumps({"strategy_name": "test"}))

        output_zip = base_path / "bundle.zip"

        exporter = StrategyExporter(
            strategy_name="test",
            artifact_directory=str(base_path),
            output_zip_path=str(output_zip),
            readiness_report_path=str(readiness),
        )

        bundle = exporter.create_bundle()

        assert "readiness_report.json" in bundle.files