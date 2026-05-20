"""Tests for genetic optimizer."""

import pytest
from unittest.mock import MagicMock

from aurora.optimization.advanced.genetic import GeneticOptimizer
from aurora.optimization import BestParameters


def create_param_space() -> dict:
    return {
        "fast_window": {"type": "int", "low": 5, "high": 15, "step": 1},
        "slow_window": {"type": "int", "low": 20, "high": 30, "step": 5},
    }


def test_genetic_optimizer_initialization() -> None:
    """Test genetic optimizer initializes correctly."""
    param_space = create_param_space()

    def fitness_fn(params):
        return params["fast_window"] / params["slow_window"]

    optimizer = GeneticOptimizer(
        param_space=param_space,
        fitness_fn=fitness_fn,
        population_size=10,
        generations=5,
    )

    assert optimizer.population_size == 10
    assert optimizer.generations == 5
    assert optimizer.param_space == param_space


def test_genetic_optimizer_optimize() -> None:
    """Test genetic optimizer runs and returns best params."""
    param_space = create_param_space()

    call_count = 0

    def fitness_fn(params):
        nonlocal call_count
        call_count += +1
        return params["fast_window"] / params["slow_window"]

    optimizer = GeneticOptimizer(
        param_space=param_space,
        fitness_fn=fitness_fn,
        population_size=10,
        generations=3,
        random_seed=42,
    )

    result = optimizer.optimize()

    assert isinstance(result, BestParameters)
    assert result.parameters is not None
    assert result.fitness >= 0
    assert len(result.fitness_history) == 3
    assert call_count > 0


def test_genetic_optimizer_convergence() -> None:
    """Test that fitness improves over generations."""
    param_space = {
        "x": {"type": "int", "low": 0, "high": 100, "step": 1},
    }

    def fitness_fn(params):
        return 100 - abs(params["x"] - 50)

    optimizer = GeneticOptimizer(
        param_space=param_space,
        fitness_fn=fitness_fn,
        population_size=50,
        generations=10,
        random_seed=123,
    )

    result = optimizer.optimize()

    assert result.fitness > 0
    assert result.fitness_history[0] <= result.fitness_history[-1] or len(set(result.fitness_history)) == 1


def test_genetic_optimizer_discrete_params() -> None:
    """Test optimizer works with discrete parameters."""
    param_space = {
        "strategy_type": {"type": "discrete", "values": ["trend", "mean_reversion", "breakout"]},
    }

    def fitness_fn(params):
        return {"trend": 0.8, "mean_reversion": 0.6, "breakout": 0.7}[params["strategy_type"]]

    optimizer = GeneticOptimizer(
        param_space=param_space,
        fitness_fn=fitness_fn,
        population_size=10,
        generations=3,
        random_seed=42,
    )

    result = optimizer.optimize()

    assert result.parameters["strategy_type"] in ["trend", "mean_reversion", "breakout"]


def test_genetic_optimizer_with_float_params() -> None:
    """Test optimizer works with float parameters."""
    param_space = {
        "threshold": {"type": "float", "low": 0.0, "high": 1.0},
    }

    def fitness_fn(params):
        return 1.0 - abs(params["threshold"] - 0.5)

    optimizer = GeneticOptimizer(
        param_space=param_space,
        fitness_fn=fitness_fn,
        population_size=20,
        generations=3,
        random_seed=42,
    )

    result = optimizer.optimize()

    assert 0.0 <= result.parameters["threshold"] <= 1.0


def test_genetic_optimizer_best_params_to_dict() -> None:
    """Test BestParameters to_dict method."""
    param_space = create_param_space()

    def fitness_fn(params):
        return 0.5

    optimizer = GeneticOptimizer(
        param_space=param_space,
        fitness_fn=fitness_fn,
        population_size=5,
        generations=2,
    )

    result = optimizer.optimize()
    result_dict = result.to_dict()

    assert "parameters" in result_dict
    assert "fitness" in result_dict
    assert "fitness_history" in result_dict