"""Tests for Bayesian optimizer."""

import sys
import pytest
from unittest.mock import MagicMock, patch

from aurora.optimization import BestParameters


def create_param_space() -> dict:
    return {
        "fast_window": {"type": "int", "low": 5, "high": 15, "step": 1},
        "slow_window": {"type": "int", "low": 20, "high": 30, "step": 5},
    }


def test_bayesian_optimizer_import_error() -> None:
    """Test BayesianOptimizer raises ImportError when Optuna not installed."""
    optuna_module = sys.modules.pop("optuna", None)
    try:
        from aurora.optimization.advanced.bayesian import BayesianOptimizer, OptunaNotInstalledError
        param_space = create_param_space()

        def fitness_fn(params):
            return 0.5

        with pytest.raises(OptunaNotInstalledError, match="Optuna not installed"):
            BayesianOptimizer(param_space=param_space, fitness_fn=fitness_fn)
    finally:
        if optuna_module:
            sys.modules["optuna"] = optuna_module


def test_bayesian_optimizer_initialization() -> None:
    """Test Bayesian optimizer initializes correctly when Optuna available."""
    optuna_mock = MagicMock()
    sys.modules["optuna"] = optuna_mock
    try:
        from aurora.optimization.advanced.bayesian import BayesianOptimizer

        param_space = create_param_space()

        def fitness_fn(params):
            return params["fast_window"] / params["slow_window"]

        optimizer = BayesianOptimizer(
            param_space=param_space,
            fitness_fn=fitness_fn,
            n_trials=50,
            direction="maximize",
        )

        assert optimizer.n_trials == 50
        assert optimizer.direction == "maximize"
    finally:
        if "optuna" in sys.modules:
            del sys.modules["optuna"]


def test_bayesian_optimizer_optimize() -> None:
    """Test Bayesian optimizer runs and returns best params."""
    optuna_mock = MagicMock()
    mock_study = MagicMock()
    mock_study.best_params = {"fast_window": 10, "slow_window": 25}
    mock_study.best_value = 0.4
    mock_study.trials = [MagicMock(value=0.3), MagicMock(value=0.4), MagicMock(value=0.35)]
    optuna_mock.create_study.return_value = mock_study
    optuna_mock.samplers.TPESampler.return_value = MagicMock()

    sys.modules["optuna"] = optuna_mock
    try:
        from aurora.optimization.advanced.bayesian import BayesianOptimizer

        param_space = create_param_space()

        def fitness_fn(params):
            return params["fast_window"] / params["slow_window"]

        optimizer = BayesianOptimizer(
            param_space=param_space,
            fitness_fn=fitness_fn,
            n_trials=10,
        )

        result = optimizer.optimize()

        assert isinstance(result, BestParameters)
        assert result.parameters is not None
        assert result.trials == 10
    finally:
        if "optuna" in sys.modules:
            del sys.modules["optuna"]


def test_bayesian_optimizer_discrete_params() -> None:
    """Test optimizer works with discrete parameters."""
    optuna_mock = MagicMock()
    mock_study = MagicMock()
    mock_study.best_params = {"strategy_type": "trend"}
    mock_study.best_value = 0.8
    mock_study.trials = [MagicMock(value=0.8)]
    optuna_mock.create_study.return_value = mock_study
    optuna_mock.samplers.TPESampler.return_value = MagicMock()

    sys.modules["optuna"] = optuna_mock
    try:
        from aurora.optimization.advanced.bayesian import BayesianOptimizer

        param_space = {
            "strategy_type": {"type": "discrete", "values": ["trend", "mean_reversion"]},
        }

        def fitness_fn(params):
            return {"trend": 0.8, "mean_reversion": 0.6}[params["strategy_type"]]

        optimizer = BayesianOptimizer(
            param_space=param_space,
            fitness_fn=fitness_fn,
            n_trials=5,
        )

        result = optimizer.optimize()

        assert result.parameters["strategy_type"] in ["trend", "mean_reversion"]
    finally:
        if "optuna" in sys.modules:
            del sys.modules["optuna"]