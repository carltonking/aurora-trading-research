"""Universe management for multi-asset trading.

This module provides research-only universe management. No live trading, no broker calls.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass
class Universe:
    """A collection of symbols for multi-asset trading."""

    name: str
    symbols: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "symbols": self.symbols,
            "metadata": self.metadata,
        }


class UniverseProvider:
    """Provider for creating and managing universes."""

    @staticmethod
    def from_list(name: str, symbols: list[str]) -> Universe:
        """Create a universe from a list of symbols.

        Args:
            name: Name of the universe.
            symbols: List of ticker symbols.

        Returns:
            Universe instance.
        """
        return Universe(name=name, symbols=symbols)

    @staticmethod
    def from_file(path: str) -> Universe:
        """Create a universe from a JSON file.

        The file should contain a JSON object with 'name' and 'symbols' keys,
        or a simple list of symbols.

        Args:
            path: Path to the JSON file.

        Returns:
            Universe instance.
        """
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Universe file not found: {path}")

        with file_path.open() as f:
            data = json.load(f)

        if isinstance(data, list):
            return Universe(name=file_path.stem, symbols=data)
        elif isinstance(data, dict):
            return Universe(
                name=data.get("name", file_path.stem),
                symbols=data.get("symbols", []),
                metadata=data.get("metadata", {}),
            )
        else:
            raise ValueError(f"Invalid universe file format: {path}")

    @staticmethod
    def fetch_data(
        universe: Universe,
        start_date: str,
        end_date: str,
        data_source: Any = None,
    ) -> dict[str, pd.DataFrame]:
        """Fetch OHLCV data for all symbols in a universe.

        Args:
            universe: Universe to fetch data for.
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).
            data_source: Optional data source. If None, uses YFinanceDataSource.

        Returns:
            Dict mapping symbol to DataFrame with OHLCV data.
        """
        from aurora.data.yfinance_source import YFinanceDataSource

        if data_source is None:
            data_source = YFinanceDataSource()

        results = {}
        errors = []

        for symbol in universe.symbols:
            try:
                data = data_source.fetch(
                    symbols=[symbol],
                    start_date=start_date,
                    end_date=end_date,
                )
                if data is not None and not data.empty:
                    results[symbol] = data
                else:
                    errors.append(f"No data for {symbol}")
            except Exception as e:
                errors.append(f"Failed to fetch {symbol}: {e}")

        if errors:
            print(f"[yellow]Warning:[/yellow] {len(errors)} symbols failed to fetch:")
            for error in errors[:5]:
                print(f"  - {error}")
            if len(errors) > 5:
                print(f"  ... and {len(errors) - 5} more")

        return results


def create_universe_from_symbols(symbols: list[str], name: str = "custom") -> Universe:
    """Convenience function to create a universe from symbols.

    Args:
        symbols: List of ticker symbols.
        name: Name for the universe.

    Returns:
        Universe instance.
    """
    return UniverseProvider.from_list(name, symbols)