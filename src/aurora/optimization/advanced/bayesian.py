"""Bayesian optimization using Optuna."""

from typing import Any, Callable

from aurora.optimization import BestParameters


class OptunaNotInstalledError(Exception):
    """Raised when Optuna is not installed."""
    pass


class BayesianOptimizer:
    """Bayesian optimization using Optuna.

    This optimizer is research-only and does not call any broker.
    """

    def __init__(
        self,
        param_space: dict[str, dict[str, Any]],
        fitness_fn: Callable[[dict[str, Any]], float],
        n_trials: int = 100,
        direction: str = "maximize",
        random_seed: int | None = None,
    ):
        """Initialize Bayesian optimizer.

        Args:
            param_space: Dict mapping param name to config dict with:
                - type: "int", "float", or "discrete"
                - low/high/step for int/float
                - values for discrete
            fitness_fn: Function taking param dict, returns fitness float.
            n_trials: Number of optimization trials.
            direction: "maximize" or "minimize".
            random_seed: Optional seed for reproducibility.
        """
        try:
            import optuna
        except ImportError:
            raise OptunaNotInstalledError(
                "Optuna not installed. Install with: pip install optuna"
            )

        self.param_space = param_space
        self.fitness_fn = fitness_fn
        self.n_trials = n_trials
        self.direction = direction
        self.random_seed = random_seed
        self._optuna = optuna

    def optimize(self) -> BestParameters:
        """Run Bayesian optimization.

        Returns:
            BestParameters with best found parameters and fitness.
        """
        study = self._optuna.create_study(
            direction=self.direction,
            sampler=self._optuna.samplers.TPESampler(seed=self.random_seed),
        )

        study.optimize(
            self._objective,
            n_trials=self.n_trials,
            show_progress_bar=False,
        )

        fitness_history = [
            trial.value for trial in study.trials if trial.value is not None
        ]

        return BestParameters(
            parameters=study.best_params,
            fitness=study.best_value if study.best_value is not None else 0.0,
            fitness_history=fitness_history,
            trials=self.n_trials,
        )

    def _objective(self, trial: Any) -> float:
        """Optuna objective function."""
        params = {}

        for param_name, config in self.param_space.items():
            if config["type"] == "int":
                low = config["low"]
                high = config["high"]
                step = config.get("step", 1)
                values = list(range(low, high + 1, step))
                params[param_name] = trial.suggest_int(param_name, min(values), max(values), step=step)

            elif config["type"] == "float":
                low = config["low"]
                high = config["high"]
                params[param_name] = trial.suggest_float(param_name, low, high)

            elif config["type"] == "discrete":
                values = config["values"]
                params[param_name] = trial.suggest_categorical(param_name, values)

        return self.fitness_fn(params)