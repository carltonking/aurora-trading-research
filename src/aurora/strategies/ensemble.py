"""Ensemble strategy - combines multiple strategies into one.

This is a research-only signal generator. No live trading, no broker calls.
"""

import pandas as pd
from typing import Any


class EnsembleStrategy:
    """Ensemble strategy that combines multiple strategies.

    Supports different combination methods: vote, weighted, unanimous.
    """

    def __init__(
        self,
        strategies: list[tuple[Any, float]],
        method: str = "vote",
        vote_threshold: float = 0.5,
        weighted_threshold: float = 0.2,
    ):
        """Initialize ensemble strategy.

        Args:
            strategies: List of (strategy_instance, weight) tuples.
            method: Combination method - "vote", "weighted", or "unanimous".
            vote_threshold: For vote method, fraction needed for majority.
            weighted_threshold: For weighted method, threshold for non-zero signal.
        """
        valid_methods = {"vote", "weighted", "unanimous"}
        if method not in valid_methods:
            raise ValueError(f"method must be one of {valid_methods}")

        if not strategies:
            raise ValueError("strategies list cannot be empty")

        total_weight = sum(w for _, w in strategies)
        if total_weight <= 0:
            raise ValueError("total weight must be positive")

        self.strategies = strategies
        self.method = method
        self.vote_threshold = vote_threshold
        self.weighted_threshold = weighted_threshold
        self.strategy_name = "ensemble"
        self._sub_strategy_names = [s.__class__.__name__ for s, _ in strategies]

    def __repr__(self) -> str:
        return (
            f"EnsembleStrategy(method={self.method}, "
            f"strategies={self._sub_strategy_names})"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        """Return merged parameters from all sub-strategies."""
        params = {"method": self.method, "sub_strategies": []}
        for strategy, weight in self.strategies:
            sub_params = {
                "name": strategy.__class__.__name__,
                "weight": weight,
            }
            if hasattr(strategy, "__dict__"):
                for key, value in strategy.__dict__.items():
                    if not key.startswith("_") and key not in ("strategy_name",):
                        sub_params[key] = value
            params["sub_strategies"].append(sub_params)
        return params

    def generate_signal(self, data: pd.DataFrame) -> pd.Series:
        """Generate ensemble signal from underlying strategies.

        Args:
            data: DataFrame with price data.

        Returns:
            Series with ensemble signals: -1, 0, or 1.
        """
        signals = []
        for strategy, weight in self.strategies:
            sig = strategy.generate_signal(data)
            sig = self._normalize_signal(sig)
            signals.append((sig, weight))

        if self.method == "vote":
            return self._vote_signals(signals)
        elif self.method == "weighted":
            return self._weighted_signals(signals)
        elif self.method == "unanimous":
            return self._unanimous_signals(signals)

        return pd.Series(0, index=data.index)

    def _normalize_signal(self, signal: pd.Series) -> pd.Series:
        """Normalize continuous signals to -1, 0, 1."""
        result = signal.copy()
        result = result.apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
        return result

    def _vote_signals(self, signals: list[tuple[pd.Series, float]]) -> pd.Series:
        """Combine signals using voting (mode)."""
        data_index = signals[0][0].index
        n = len(data_index)
        result = pd.Series(0, index=data_index)

        for i in range(n):
            votes = {-1: 0.0, 0.0: 0.0, 1.0: 0.0}
            for sig, weight in signals:
                val = sig.iloc[i]
                if val in votes:
                    votes[val] += weight

            total = sum(votes.values())
            if total > 0:
                for v in [-1, 0, 1]:
                    if votes[v] / total >= self.vote_threshold:
                        result.iloc[i] = v
                        break

        return result

    def _weighted_signals(self, signals: list[tuple[pd.Series, float]]) -> pd.Series:
        """Combine signals using weighted sum."""
        data_index = signals[0][0].index
        n = len(data_index)
        result = pd.Series(0, index=data_index)

        total_weight = sum(w for _, w in self.strategies)

        for i in range(n):
            weighted_sum = sum(sig.iloc[i] * weight for sig, weight in signals)
            normalized = weighted_sum / total_weight

            if normalized > self.weighted_threshold:
                result.iloc[i] = 1
            elif normalized < -self.weighted_threshold:
                result.iloc[i] = -1

        return result

    def _unanimous_signals(self, signals: list[tuple[pd.Series, float]]) -> pd.Series:
        """Combine signals requiring unanimous agreement."""
        data_index = signals[0][0].index
        n = len(data_index)
        result = pd.Series(0, index=data_index)

        for i in range(n):
            first_val = int(signals[0][0].iloc[i])
            if first_val == 0:
                result.iloc[i] = 0
                continue

            all_same = all(int(sig.iloc[i]) == first_val for sig, _ in signals)
            if all_same:
                result.iloc[i] = first_val

        return result