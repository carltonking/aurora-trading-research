"""Genetic algorithm optimizer."""

import random
from dataclasses import dataclass
from typing import Any, Callable

from aurora.optimization import BestParameters


@dataclass
class GeneticOptimizer:
    """Genetic algorithm for hyperparameter optimization.

    This optimizer is research-only and does not call any broker.
    """

    def __init__(
        self,
        param_space: dict[str, dict[str, Any]],
        fitness_fn: Callable[[dict[str, Any]], float],
        population_size: int = 50,
        generations: int = 20,
        mutation_rate: float = 0.1,
        crossover_rate: float = 0.7,
        random_seed: int | None = None,
    ):
        """Initialize genetic optimizer.

        Args:
            param_space: Dict mapping param name to config dict with:
                - type: "int", "float", or "discrete"
                - low/high/step for int/float
                - values for discrete
            fitness_fn: Function taking param dict, returns fitness float.
            population_size: Number of individuals in population.
            generations: Number of generations to evolve.
            mutation_rate: Probability of mutating a parameter.
            crossover_rate: Probability of crossover between parents.
            random_seed: Optional seed for reproducibility.
        """
        self.param_space = param_space
        self.fitness_fn = fitness_fn
        self.population_size = population_size
        self.generations = generations
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate

        if random_seed is not None:
            random.seed(random_seed)

    def optimize(self) -> BestParameters:
        """Run genetic algorithm optimization.

        Returns:
            BestParameters with best found parameters and fitness.
        """
        population = self._initialize_population()
        best_fitness = float("-inf")
        best_params = None
        fitness_history = []

        for gen in range(self.generations):
            fitnesses = []
            for individual in population:
                fitness = self.fitness_fn(individual)
                fitnesses.append(fitness)

                if fitness > best_fitness:
                    best_fitness = fitness
                    best_params = individual.copy()

            fitness_history.append(best_fitness)

            population = self._evolve_population(population, fitnesses)

        return BestParameters(
            parameters=best_params,
            fitness=best_fitness,
            fitness_history=fitness_history,
            generations=self.generations,
        )

    def _initialize_population(self) -> list[dict[str, Any]]:
        """Generate initial random population."""
        population = []
        for _ in range(self.population_size):
            individual = {}
            for param_name, config in self.param_space.items():
                if config["type"] == "int":
                    low = config["low"]
                    high = config["high"]
                    step = config.get("step", 1)
                    values = list(range(low, high + 1, step))
                    individual[param_name] = random.choice(values)
                elif config["type"] == "float":
                    low = config["low"]
                    high = config["high"]
                    step = config.get("step", (high - low) / 10)
                    values = [low + i * step for i in range(int((high - low) / step) + 1)]
                    individual[param_name] = random.choice(values)
                elif config["type"] == "discrete":
                    individual[param_name] = random.choice(config["values"])
            population.append(individual)
        return population

    def _evolve_population(
        self,
        population: list[dict[str, Any]],
        fitnesses: list[float],
    ) -> list[dict[str, Any]]:
        """Evolve population through selection, crossover, and mutation."""
        new_population = []

        sorted_indices = sorted(range(len(fitnesses)), key=lambda i: fitnesses[i], reverse=True)
        elites = [population[i] for i in sorted_indices[:max(1, self.population_size // 10)]]
        new_population.extend(elites)

        while len(new_population) < self.population_size:
            parent1 = self._tournament_select(population, fitnesses)
            parent2 = self._tournament_select(population, fitnesses)

            if random.random() < self.crossover_rate:
                child = self._crossover(parent1, parent2)
            else:
                child = parent1.copy()

            if random.random() < self.mutation_rate:
                child = self._mutate(child)

            new_population.append(child)

        return new_population[: self.population_size]

    def _tournament_select(
        self,
        population: list[dict[str, Any]],
        fitnesses: list[float],
    ) -> dict[str, Any]:
        """Tournament selection."""
        k = max(2, self.population_size // 5)
        indices = random.sample(range(len(population)), k)
        best_idx = max(indices, key=lambda i: fitnesses[i])
        return population[best_idx].copy()

    def _crossover(
        self,
        parent1: dict[str, Any],
        parent2: dict[str, Any],
    ) -> dict[str, Any]:
        """Single-point crossover."""
        child = {}
        for param_name in self.param_space.keys():
            if random.random() < 0.5:
                child[param_name] = parent1[param_name]
            else:
                child[param_name] = parent2[param_name]
        return child

    def _mutate(self, individual: dict[str, Any]) -> dict[str, Any]:
        """Mutate individual parameters."""
        mutated = individual.copy()
        for param_name, config in self.param_space.items():
            if config["type"] == "int":
                low = config["low"]
                high = config["high"]
                step = config.get("step", 1)
                values = list(range(low, high + 1, step))
                mutated[param_name] = random.choice(values)
            elif config["type"] == "float":
                low = config["low"]
                high = config["high"]
                step = config.get("step", (high - low) / 10)
                values = [low + i * step for i in range(int((high - low) / step) + 1)]
                mutated[param_name] = random.choice(values)
            elif config["type"] == "discrete":
                mutated[param_name] = random.choice(config["values"])
        return mutated