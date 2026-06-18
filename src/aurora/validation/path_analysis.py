"""Path analysis for CPCV results.

Provides visualization and statistical analysis tools for Combinatorial Purged
Cross-Validation results. Includes equity curve plotting, Deflated Sharpe Ratio,
and strategy selection bias scoring.

This module is research-only. No live trading, no broker calls.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np


MANDATORY_DISCLAIMER = (
    "CPCV path analysis is a research tool for estimating backtest overfitting risk. "
    "Results are not profitability guarantees. AURORA is research-only. "
    "Past performance does not guarantee future results."
)


def plot_equity_curves(
    paths: list[dict[str, Any]],
    title: str = "CPCV Equity Curves",
    show: bool = False,
    output_path: str | None = None,
) -> dict[str, Any]:
    """Render overlapping equity curves for multiple CPCV paths.

    Makes regime sensitivity visually obvious by plotting all paths
    on the same chart with the median path highlighted.

    Args:
        paths: List of BacktestPathResult dicts with equity_curve and path_id.
        title: Chart title.
        show: Whether to display the plot interactively.
        output_path: Optional path to save the figure.

    Returns:
        Dictionary with plot metadata and path statistics.
    """
    try:
        import matplotlib.pyplot as plt
        import matplotlib.colors as mcolors
    except ImportError:
        return {
            "error": "matplotlib not available",
            "disclaimer": MANDATORY_DISCLAIMER,
        }

    if not paths:
        return {
            "error": "no paths provided",
            "disclaimer": MANDATORY_DISCLAIMER,
        }

    fig, ax = plt.subplots(figsize=(12, 7))

    colors = list(mcolors.TABLEAU_COLORS.values())
    equity_arrays = []

    for i, path in enumerate(paths):
        equity_curve = path.get("equity_curve", [])
        if not equity_curve:
            continue
        equity_arr = np.array(equity_curve)
        if len(equity_arr) < 2:
            continue
        normalized = equity_arr / equity_arr[0]
        color = colors[i % len(colors)]
        ax.plot(normalized, color=color, alpha=0.35, linewidth=0.8, label=f"Path {path.get('path_id', i)}")
        equity_arrays.append(normalized)

    if equity_arrays:
        max_len = max(len(e) for e in equity_arrays)
        padded = np.zeros((len(equity_arrays), max_len))
        for j, e in enumerate(equity_arrays):
            padded[j, :len(e)] = e

        median_curve = np.median(padded, axis=0)
        ax.plot(median_curve, color="black", linewidth=2.5, linestyle="--", label="Median Path")

        mean_curve = np.mean(padded, axis=0)
        ax.plot(mean_curve, color="navy", linewidth=1.5, linestyle="-.", label="Mean Path")

        min_curve = np.min(padded, axis=0)
        max_curve = np.max(padded, axis=0)
        ax.fill_between(range(len(min_curve)), min_curve, max_curve, alpha=0.15, color="gray", label="Path Range")

    ax.axhline(y=1.0, color="gray", linestyle=":", linewidth=1)
    ax.set_xlabel("Period")
    ax.set_ylabel("Normalized Equity (1.0 = initial)")
    ax.set_title(f"{title}\n{MANDATORY_DISCLAIMER}")
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    if output_path:
        try:
            fig.savefig(output_path, dpi=150, bbox_inches="tight")
        except Exception:
            pass

    if show:
        try:
            plt.show()
        except Exception:
            pass
    else:
        plt.close(fig)

    sharpes = [p.get("sharpe_ratio", 0.0) for p in paths]
    returns = [p.get("total_return", 0.0) for p in paths]

    return {
        "title": title,
        "n_paths": len(paths),
        "mean_sharpe": float(np.mean(sharpes)) if sharpes else 0.0,
        "std_sharpe": float(np.std(sharpes, ddof=1)) if len(sharpes) > 1 else 0.0,
        "min_sharpe": float(np.min(sharpes)) if sharpes else 0.0,
        "max_sharpe": float(np.max(sharpes)) if sharpes else 0.0,
        "median_return": float(np.median(returns)) if returns else 0.0,
        "disclaimer": MANDATORY_DISCLAIMER,
        "output_path": output_path,
    }


# Euler-Mascheroni constant, used in the expected-maximum-Sharpe benchmark.
_EULER_MASCHERONI = 0.5772156649015329


def expected_max_sharpe(n_trials: int, sharpe_std: float) -> float:
    """Expected maximum Sharpe ratio under the null hypothesis of zero edge.

    This is the SR0 benchmark from López de Prado (2014), "The Deflated Sharpe
    Ratio". Given ``n_trials`` independent strategy configurations whose Sharpe
    estimates are drawn from a distribution with standard deviation
    ``sharpe_std``, the expected maximum of those estimates (under a null of no
    skill) is::

        SR0 = sharpe_std * [ (1 - gamma) * Z(1 - 1/N)
                             + gamma     * Z(1 - 1/(N*e)) ]

    where ``gamma`` is the Euler-Mascheroni constant, ``Z`` is the inverse
    standard-normal CDF (``norm.ppf``), ``N`` is the number of trials, and ``e``
    is Euler's number. SR0 grows with the number of trials: the more
    configurations you search over, the higher a Sharpe you expect to find by
    luck alone, and the higher the bar a genuine strategy must clear.

    Args:
        n_trials: Number of strategy configurations / paths tested.
        sharpe_std: Standard deviation of the trial Sharpe estimates.

    Returns:
        The expected-maximum Sharpe benchmark SR0 (>= 0).
    """
    from scipy import stats

    n = max(int(n_trials), 1)
    if sharpe_std <= 0.0 or n <= 1:
        return 0.0

    gamma = _EULER_MASCHERONI
    # Z(1 - 1/N): the expected location of the max of N standard normals.
    z1 = stats.norm.ppf(1.0 - 1.0 / n)
    # Z(1 - 1/(N*e)): second-order correction term.
    z2 = stats.norm.ppf(1.0 - 1.0 / (n * math.e))
    sr0 = sharpe_std * ((1.0 - gamma) * z1 + gamma * z2)
    return float(max(0.0, sr0))


def deflated_sharpe_ratio(
    observed_sharpe: float,
    n_paths: int,
    sharpe_std: float = 0.0,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
    n_observations: int = 252,
) -> float:
    """Compute the Deflated Sharpe Ratio (DSR) — López de Prado (2014).

    The DSR is the probability that the observed Sharpe ratio exceeds the
    expected-maximum Sharpe achievable by chance, after accounting for the
    number of trials and the non-normality (skew, kurtosis) of the returns. It
    is the canonical implementation; ``cpcv.deflated_sharpe_ratio`` delegates
    here.

    Formula::

        SR0 = expected_max_sharpe(N, sigma_SR)
        DSR = Phi( ((SR - SR0) * sqrt(T - 1))
                   / sqrt(1 - skew*SR + ((kurt - 1)/4) * SR^2) )

    where ``Phi`` is the standard-normal CDF (``norm.cdf``), ``T`` is the number
    of return observations, ``skew``/``kurt`` are the skewness and kurtosis of
    the return series, ``SR`` is the observed (non-annualized, per-observation)
    Sharpe, and ``SR0`` is the expected-maximum-Sharpe benchmark under the null.

    Properties guaranteed by this implementation:
      * DSR in [0, 1] (it is a probability).
      * DSR decreases as the number of trials N increases (multiple-testing
        penalty: SR0 rises with N, shrinking the numerator).
      * DSR increases with a higher observed Sharpe.

    Args:
        observed_sharpe: Observed Sharpe ratio (same scale as ``sharpe_std``).
        n_paths: Number of trials / CPCV paths tested.
        sharpe_std: Standard deviation of the trial Sharpe estimates.
        skewness: Skewness of the return series (3rd standardized moment).
        kurtosis: Kurtosis of the return series (4th standardized moment; 3.0
            for a normal distribution).
        n_observations: Number of return observations T behind the Sharpe.

    Returns:
        Deflated Sharpe Ratio as a probability in [0, 1].
    """
    from scipy import stats

    t = int(n_observations)
    if t < 2:
        return 0.0

    sr = float(observed_sharpe)
    sr0 = expected_max_sharpe(n_paths, sharpe_std)

    # Variance scaling of the Sharpe estimator under non-normal returns
    # (Mertens / López de Prado). For normal returns (skew=0, kurt=3) this
    # reduces to 1, recovering the classic sqrt(T-1) scaling.
    variance_term = 1.0 - skewness * sr + ((kurtosis - 1.0) / 4.0) * sr * sr
    if variance_term <= 0.0:
        # Degenerate moment estimates — fall back to the normal-returns case
        # rather than producing a NaN.
        variance_term = 1.0

    z = (sr - sr0) * math.sqrt(t - 1) / math.sqrt(variance_term)
    dsr = stats.norm.cdf(z)
    return float(dsr)


def strategy_selection_bias_score(
    observed_sharpe: float,
    mean_path_sharpe: float,
    best_path_sharpe: float,
    n_paths: int,
) -> float:
    """Estimate selection bias in strategy path selection.

    A high score indicates the observed Sharpe may largely be explained
    by cherry-picking the best backtest path rather than genuine edge.

    Args:
        observed_sharpe: Sharpe from full backtest.
        mean_path_sharpe: Mean Sharpe across CPCV paths.
        best_path_sharpe: Best Sharpe across CPCV paths.
        n_paths: Number of paths tested.

    Returns:
        Bias score between 0 (no bias) and 1 (extreme bias).
    """
    if best_path_sharpe <= mean_path_sharpe or n_paths < 2:
        return 0.0

    spread = best_path_sharpe - mean_path_sharpe
    advantage = observed_sharpe - mean_path_sharpe

    if advantage <= 0:
        return 1.0

    ratio = advantage / spread if spread > 0 else 0.0
    path_penalty = math.log(float(n_paths)) / float(n_paths)
    bias = ratio * path_penalty

    return min(1.0, max(0.0, bias))


def compute_probabilistic_sharpe_ratio(
    observed_sharpe: float,
    sharpe_std: float,
    n_observations: int = 252,
    benchmark_sharpe: float = 0.0,
) -> float:
    """Compute Probabilistic Sharpe Ratio (PSR).

    The probability that the observed Sharpe is greater than the benchmark,
    assuming Sharpe follows a normal distribution with estimated moments.

    Args:
        observed_sharpe: Observed Sharpe ratio.
        sharpe_std: Standard deviation of Sharpe.
        n_observations: Number of observations (default 252 for annual).
        benchmark_sharpe: Benchmark Sharpe to compare against.

    Returns:
        PSR value (probability-like, typically 0 to 1).
    """
    if sharpe_std <= 1e-10 or n_observations < 2:
        return 0.5

    try:
        from scipy import stats
        z = (observed_sharpe - benchmark_sharpe) / (sharpe_std / math.sqrt(n_observations))
        psr = stats.norm.cdf(z)
        return float(psr)
    except ImportError:
        z_manual = (observed_sharpe - benchmark_sharpe) * math.sqrt(n_observations) / sharpe_std
        psr_manual = 0.5 * (1.0 + math.erf(z_manual / math.sqrt(2)))
        return max(0.0, min(1.0, psr_manual))


def path_heatmap(
    paths: list[dict[str, Any]],
    output_path: str | None = None,
) -> dict[str, Any]:
    """Generate a heatmap of path returns across time periods.

    Args:
        paths: List of BacktestPathResult dicts.
        output_path: Optional path to save the figure.

    Returns:
        Dictionary with heatmap metadata.
    """
    try:
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        return {
            "error": "matplotlib or numpy not available",
            "disclaimer": MANDATORY_DISCLAIMER,
        }

    if not paths:
        return {"error": "no paths", "disclaimer": MANDATORY_DISCLAIMER}

    equity_arrays = []
    for path in paths:
        equity_curve = path.get("equity_curve", [])
        if equity_curve and len(equity_curve) > 1:
            normalized = np.array(equity_curve) / np.array(equity_curve[0])
            equity_arrays.append(normalized)

    if not equity_arrays:
        return {"error": "no valid equity curves", "disclaimer": MANDATORY_DISCLAIMER}

    max_len = max(len(e) for e in equity_arrays)
    padded = np.zeros((len(equity_arrays), max_len))
    for i, e in enumerate(equity_arrays):
        padded[i, :len(e)] = e

    fig, ax = plt.subplots(figsize=(14, 5))
    im = ax.imshow(padded, aspect="auto", cmap="RdYlGn", interpolation="nearest")
    ax.set_xlabel("Period")
    ax.set_ylabel("Path")
    ax.set_title(f"CPCV Path Heatmap\n{MANDATORY_DISCLAIMER}")
    ax.set_yticks(range(len(paths)))
    ax.set_yticklabels([f"P{p.get('path_id', i)}" for i, p in enumerate(paths)])
    plt.colorbar(im, ax=ax, label="Normalized Equity")

    if output_path:
        try:
            fig.savefig(output_path, dpi=150, bbox_inches="tight")
        except Exception:
            pass

    plt.close(fig)

    return {
        "n_paths": len(paths),
        "max_periods": max_len,
        "disclaimer": MANDATORY_DISCLAIMER,
        "output_path": output_path,
    }