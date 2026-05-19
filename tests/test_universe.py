"""Tests for universe module."""

import json
import tempfile
from pathlib import Path

import pytest

from aurora.data.universe import Universe, UniverseProvider, create_universe_from_symbols


def test_universe_creation() -> None:
    """Test creating a universe."""
    universe = Universe(name="test", symbols=["AAPL", "MSFT", "GOOGL"])

    assert universe.name == "test"
    assert len(universe.symbols) == 3
    assert "AAPL" in universe.symbols


def test_universe_to_dict() -> None:
    """Test converting universe to dict."""
    universe = Universe(name="test", symbols=["AAPL", "MSFT"])

    data = universe.to_dict()

    assert data["name"] == "test"
    assert data["symbols"] == ["AAPL", "MSFT"]


def test_universe_from_list() -> None:
    """Test creating universe from list."""
    universe = UniverseProvider.from_list("my_universe", ["AAPL", "MSFT", "GOOGL"])

    assert universe.name == "my_universe"
    assert len(universe.symbols) == 3


def test_universe_from_file_with_list() -> None:
    """Test loading universe from JSON file with list."""
    with tempfile.TemporaryDirectory() as tmpdir:
        universe_file = Path(tmpdir) / "universe.json"
        universe_file.write_text(json.dumps(["AAPL", "MSFT", "GOOGL"]))

        universe = UniverseProvider.from_file(str(universe_file))

        assert universe.name == "universe"
        assert len(universe.symbols) == 3


def test_universe_from_file_with_dict() -> None:
    """Test loading universe from JSON file with dict."""
    with tempfile.TemporaryDirectory() as tmpdir:
        universe_file = Path(tmpdir) / "universe.json"
        with universe_file.open("w") as f:
            json.dump({
                "name": "tech_stocks",
                "symbols": ["AAPL", "MSFT", "GOOGL"],
                "metadata": {"description": "Technology stocks"}
            }, f)

        universe = UniverseProvider.from_file(str(universe_file))

        assert universe.name == "tech_stocks"
        assert len(universe.symbols) == 3
        assert universe.metadata["description"] == "Technology stocks"


def test_universe_from_file_not_found() -> None:
    """Test that missing file raises error."""
    with pytest.raises(FileNotFoundError):
        UniverseProvider.from_file("/nonexistent/path.json")


def test_create_universe_from_symbols() -> None:
    """Test convenience function."""
    universe = create_universe_from_symbols(["AAPL", "MSFT"], "custom")

    assert universe.name == "custom"
    assert len(universe.symbols) == 2