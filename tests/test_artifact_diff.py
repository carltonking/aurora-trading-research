"""Tests for artifact diffing system."""

import json
import os
import pytest
import tempfile
from pathlib import Path

from aurora.reporting.artifact_diff import (
    ArtifactDiffer,
    diff_dicts,
    create_differ,
)


def test_diff_dicts_added_keys() -> None:
    """Test diff detects added keys."""
    old = {"a": 1, "b": 2}
    new = {"a": 1, "b": 2, "c": 3}

    result = diff_dicts(old, new)

    assert "c" in result["added"]
    assert "c" not in result["removed"]


def test_diff_dicts_removed_keys() -> None:
    """Test diff detects removed keys."""
    old = {"a": 1, "b": 2, "c": 3}
    new = {"a": 1, "b": 2}

    result = diff_dicts(old, new)

    assert "c" in result["removed"]
    assert "c" not in result["added"]


def test_diff_dicts_changed_values() -> None:
    """Test diff detects changed values."""
    old = {"a": 1, "b": 2}
    new = {"a": 10, "b": 2}

    result = diff_dicts(old, new)

    assert "a" in result["changed"]
    assert result["changed"]["a"]["old_value"] == 1
    assert result["changed"]["a"]["new_value"] == 10
    assert result["changed"]["a"]["delta"] == 9
    assert result["changed"]["a"]["percent_change"] == 900.0


def test_diff_dicts_no_change() -> None:
    """Test diff returns empty when no change."""
    old = {"a": 1, "b": 2}
    new = {"a": 1, "b": 2}

    result = diff_dicts(old, new)

    assert not result["added"]
    assert not result["removed"]
    assert not result["changed"]


def test_diff_dicts_nested() -> None:
    """Test diff detects nested changes."""
    old = {"metrics": {"sharpe": 1.0, "drawdown": 0.1}}
    new = {"metrics": {"sharpe": 1.5, "drawdown": 0.1}}

    result = diff_dicts(old, new)

    assert "metrics" in result["nested"]
    nested = result["nested"]["metrics"]
    assert "sharpe" in nested["changed"]
    assert nested["changed"]["sharpe"]["new_value"] == 1.5


def test_diff_dicts_numeric_zero_division() -> None:
    """Test diff handles zero division for percent change."""
    old = {"a": 0}
    new = {"a": 10}

    result = diff_dicts(old, new)

    assert result["changed"]["a"]["percent_change"] is None


def test_artifact_differ_disabled_by_default() -> None:
    """Test differ is disabled when env var not set."""
    differ = ArtifactDiffer("data")

    assert differ.is_enabled is False


def test_artifact_differ_enabled_with_env() -> None:
    """Test differ is enabled when env var set."""
    original = os.environ.get("AURORA_DIFF_ARTIFACTS")
    try:
        os.environ["AURORA_DIFF_ARTIFACTS"] = "true"
        differ = ArtifactDiffer("data")

        assert differ.is_enabled is True
    finally:
        if original is not None:
            os.environ["AURORA_DIFF_ARTIFACTS"] = original
        elif "AURORA_DIFF_ARTIFACTS" in os.environ:
            del os.environ["AURORA_DIFF_ARTIFACTS"]


def test_artifact_differ_save_and_get_latest() -> None:
    """Test saving and retrieving latest artifact."""
    original = os.environ.get("AURORA_DIFF_ARTIFACTS")
    try:
        os.environ["AURORA_DIFF_ARTIFACTS"] = "true"

        with tempfile.TemporaryDirectory() as tmpdir:
            differ = ArtifactDiffer(tmpdir)
            data = {"sharpe": 1.5, "drawdown": 0.1}

            differ.save_run_artifact("test_artifact", data)

            retrieved = differ.get_latest("test_artifact")
            assert retrieved == data
    finally:
        if original is not None:
            os.environ["AURORA_DIFF_ARTIFACTS"] = original
        elif "AURORA_DIFF_ARTIFACTS" in os.environ:
            del os.environ["AURORA_DIFF_ARTIFACTS"]


def test_artifact_differ_saves_previous() -> None:
    """Test that saving archives previous version."""
    original = os.environ.get("AURORA_DIFF_ARTIFACTS")
    try:
        os.environ["AURORA_DIFF_ARTIFACTS"] = "true"

        with tempfile.TemporaryDirectory() as tmpdir:
            differ = ArtifactDiffer(tmpdir)
            data_v1 = {"sharpe": 1.0, "drawdown": 0.1}

            differ.save_run_artifact("test_artifact", data_v1)

            data_v2 = {"sharpe": 1.5, "drawdown": 0.05}
            differ.save_run_artifact("test_artifact", data_v2)

            previous = differ.get_previous("test_artifact")
            assert previous == data_v1

            latest = differ.get_latest("test_artifact")
            assert latest == data_v2
    finally:
        if original is not None:
            os.environ["AURORA_DIFF_ARTIFACTS"] = original
        elif "AURORA_DIFF_ARTIFACTS" in os.environ:
            del os.environ["AURORA_DIFF_ARTIFACTS"]


def test_artifact_differ_diff_latest_no_previous() -> None:
    """Test diff when no previous version exists."""
    original = os.environ.get("AURORA_DIFF_ARTIFACTS")
    try:
        os.environ["AURORA_DIFF_ARTIFACTS"] = "true"

        with tempfile.TemporaryDirectory() as tmpdir:
            differ = ArtifactDiffer(tmpdir)
            data = {"sharpe": 1.5}

            differ.save_run_artifact("test_artifact", data)

            result = differ.diff_latest("test_artifact")

            assert result["status"] == "no_previous"
    finally:
        if original is not None:
            os.environ["AURORA_DIFF_ARTIFACTS"] = original
        elif "AURORA_DIFF_ARTIFACTS" in os.environ:
            del os.environ["AURORA_DIFF_ARTIFACTS"]


def test_artifact_differ_diff_latest_with_changes() -> None:
    """Test diff with actual changes."""
    original = os.environ.get("AURORA_DIFF_ARTIFACTS")
    try:
        os.environ["AURORA_DIFF_ARTIFACTS"] = "true"

        with tempfile.TemporaryDirectory() as tmpdir:
            differ = ArtifactDiffer(tmpdir)
            data_v1 = {"sharpe": 1.0, "drawdown": 0.1}
            data_v2 = {"sharpe": 1.5, "drawdown": 0.05}

            differ.save_run_artifact("test_artifact", data_v1)
            differ.save_run_artifact("test_artifact", data_v2)

            result = differ.diff_latest("test_artifact")

            assert "diff" in result
            diff = result["diff"]
            assert "sharpe" in diff["changed"]
            assert diff["changed"]["sharpe"]["delta"] == 0.5
    finally:
        if original is not None:
            os.environ["AURORA_DIFF_ARTIFACTS"] = original
        elif "AURORA_DIFF_ARTIFACTS" in os.environ:
            del os.environ["AURORA_DIFF_ARTIFACTS"]


def test_artifact_differ_list_history() -> None:
    """Test listing artifact history."""
    original = os.environ.get("AURORA_DIFF_ARTIFACTS")
    try:
        os.environ["AURORA_DIFF_ARTIFACTS"] = "true"

        with tempfile.TemporaryDirectory() as tmpdir:
            differ = ArtifactDiffer(tmpdir)
            data = {"value": 1}

            differ.save_run_artifact("test_artifact", data)

            history = differ.list_history("test_artifact")

            assert len(history) == 1
            assert history[0]["version"] == "latest"
    finally:
        if original is not None:
            os.environ["AURORA_DIFF_ARTIFACTS"] = original
        elif "AURORA_DIFF_ARTIFACTS" in os.environ:
            del os.environ["AURORA_DIFF_ARTIFACTS"]


def test_artifact_differ_disabled_returns_none() -> None:
    """Test save_run_artifact returns None when disabled."""
    differ = ArtifactDiffer("data")
    result = differ.save_run_artifact("test", {"a": 1})

    assert result is None


def test_create_differ_returns_none_when_disabled() -> None:
    """Test create_differ returns None when disabled."""
    original = os.environ.get("AURORA_DIFF_ARTIFACTS")
    try:
        if "AURORA_DIFF_ARTIFACTS" in os.environ:
            del os.environ["AURORA_DIFF_ARTIFACTS"]

        result = create_differ("data")
        assert result is None
    finally:
        if original is not None:
            os.environ["AURORA_DIFF_ARTIFACTS"] = original


def test_create_differ_returns_differ_when_enabled() -> None:
    """Test create_differ returns differ when enabled."""
    original = os.environ.get("AURORA_DIFF_ARTIFACTS")
    try:
        os.environ["AURORA_DIFF_ARTIFACTS"] = "true"

        result = create_differ("data")
        assert result is not None
        assert isinstance(result, ArtifactDiffer)
    finally:
        if original is not None:
            os.environ["AURORA_DIFF_ARTIFACTS"] = original
        elif "AURORA_DIFF_ARTIFACTS" in os.environ:
            del os.environ["AURORA_DIFF_ARTIFACTS"]


def test_diff_dicts_list_length_change() -> None:
    """Test diff detects list length changes."""
    old = {"trades": [1, 2, 3]}
    new = {"trades": [1, 2, 3, 4, 5]}

    result = diff_dicts(old, new)

    assert "trades" in result["changed"]
    assert result["changed"]["trades"]["length_old"] == 3
    assert result["changed"]["trades"]["length_new"] == 5