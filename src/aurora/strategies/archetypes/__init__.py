"""Strategy archetypes - template classes for config-driven strategy generation.

These archetypes are research-only signal generators. No live trading, no broker calls.
"""

from aurora.strategies.archetypes.trend_following import TrendFollowingStrategy
from aurora.strategies.archetypes.mean_reversion import MeanReversionStrategy
from aurora.strategies.archetypes.breakout import BreakoutStrategy

__all__ = [
    "TrendFollowingStrategy",
    "MeanReversionStrategy",
    "BreakoutStrategy",
]

ARCHETYPES = {
    "trend_following": TrendFollowingStrategy,
    "mean_reversion": MeanReversionStrategy,
    "breakout": BreakoutStrategy,
}


def get_archetype(name: str):
    """Get archetype class by name."""
    archetype = ARCHETYPES.get(name)
    if archetype is None:
        available = ", ".join(ARCHETYPES.keys())
        raise ValueError(f"Unknown archetype: {name}. Available: {available}")
    return archetype