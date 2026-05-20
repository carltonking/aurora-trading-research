"""Advanced optimization module."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BestParameters:
    """Result of an optimization run."""

    parameters: dict[str, Any]
    fitness: float
    fitness_history: list[float] = field(default_factory=list)
    generations: int = 0
    trials: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "parameters": self.parameters,
            "fitness": self.fitness,
            "fitness_history": self.fitness_history,
            "generations": self.generations,
            "trials": self.trials,
        }


from aurora.optimization.advanced.genetic import GeneticOptimizer
from aurora.optimization.advanced.bayesian import BayesianOptimizer

__all__ = [
    "BestParameters",
    "GeneticOptimizer",
    "BayesianOptimizer",
]