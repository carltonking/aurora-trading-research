# AURORA v3.0.0

**The methodology release.**

---

## What this is

Most backtests are broken. Not because they use wrong data — because the methodology used to produce them systematically overstates performance. The overstatement comes from three well-documented sources that are individually easy to miss and collectively devastating:

1. **Standard k-fold CV on time series data is mathematically invalid.** When you shuffle time series into folds, you train on future information and test on past information. This is not a minor technical issue — it's a category error. Nearly every open-source trading framework does it anyway.

2. **A single backtest path tells you almost nothing.** A Sharpe of 1.5 from one historical period is one sample from a distribution. Without knowing the shape of that distribution, you cannot distinguish a robust strategy from a lucky one.

3. **Testing many variants and reporting the best is selection bias.** The maximum of 50 random draws is systematically above the mean — not because the best strategy is good, but because selection amplifies noise. Naive Sharpe ratios do not account for this.

AURORA v3.0.0 ships the tools that address all three. Not as options — as defaults.

---

## What's new

### Combinatorial Purged Cross-Validation (CPCV)

Instead of partitioning data into a single train/test split, CPCV generates a combinatorial set of non-overlapping test paths with purge buffers that prevent information from leaking across the decision boundary. This produces a *distribution* of performance metrics — not a single number.

A strategy that passes CPCV across many paths is demonstrating robustness across market regimes. A strategy that succeeds in one path and fails in others is demonstrating sensitivity to the specific path that history happened to take. That distinction is the entire point.

```python
from aurora.validation.cpcv import CPCVValidator

validator = CPCVValidator(
    n_test_groups=6,
    purge_gap=5,
    embargo_fraction=0.1,
    metric="sharpe_ratio",
)
result = validator.validate(signals_df, prices_df)

print(f"CPCV Sharpe: {result.cpcv_mean:.3f} +/- {result.cpcv_std:.3f}")
print(f"Overfitting probability: {result.overfitting_prob:.3f}")
print(f"Paths: {result.n_paths}, Passes: {result.passing_paths}")
```

### Deflated Sharpe Ratio (DSR)

The Deflated Sharpe Ratio deflates the observed Sharpe by the amount you would expect from the selection process. If you tested 100 strategy variants, the best observed Sharpe is biased upward by roughly 2.5x the underlying standard deviation. DSR corrects for this.

```python
from aurora.validation.metrics import compute_deflated_sharpe

dsr = compute_deflated_sharpe(
    observed_sharpe=1.5,
    n_trials=100,
    trial_sharpe_std=0.5,
)
# DSR below zero means no actual edge after accounting for search
print(f"DSR: {dsr:.3f}")
```

A DSR below zero does not mean the strategy is bad. It means the observed Sharpe is likely the result of selection among noise.

### Automated Feature Leakage Detection

Before every backtest, AURORA runs two checks:

1. **Static AST analysis** scans feature source code for lookahead patterns — the most common is `shift(-N)`, which loads data from the future.

2. **Runtime correlation testing** computes Spearman correlations between each feature and future label values at multiple horizons. Features with statistically significant correlations beyond the intended horizon are flagged.

```python
from aurora.validation.leakage_detector import run_leakage_detection

report = run_leakage_detection(
    feature_df=features,
    label_series=labels,
    feature_files=["src/features/my_features.py"],
    horizon_days=5,
    p_value_threshold=0.001,
    bonferroni_correction=True,
    correlation_threshold=0.3,
)

if report.verdict == "COMPROMISED":
    print(f"Blocked: {report.critical_count} critical findings")
elif report.verdict == "CLEAN":
    print("Leakage check passed")
```

COMPROMISED verdict blocks the research run. SUSPECT verdict adds a warning to the manifest. CLEAN verdict is recorded with `leakage_verified: true`.

### Strategy Candidate Review Board — CPCV Thresholds

The Review Board now evaluates CPCV overfitting probability and DSR alongside existing Sharpe/drawdown/win rate thresholds. All thresholds are deterministic rules — not human judgment.

---

## Who this is for

AURORA is built for researchers who understand that backtesting without proper methodology produces numbers that look precise while telling you almost nothing. It is not a platform for generating impressive-looking backtests quickly. It is a framework for evaluating whether a strategy has genuine edge after accounting for the ways that research can be wrong in a direction that favors your hypothesis.

If you are building trading strategies and you are not using CPCV, DSR, and automated leakage detection, your backtest results are probably overstating performance in a direction that favors your hypothesis.

---

## What this is not

- **Not a money printer.** AURORA does not guarantee profitable strategies. The tools it provides help you avoid fooling yourself. They do not guarantee that what you find is real.
- **Not live trading.** AURORA is research-only and paper-trading-first. No live broker execution.
- **Not a substitute for domain knowledge.** The methodology catches common forms of overfitting and leakage. It cannot catch strategy logic errors, poor feature engineering decisions, or market regime shifts that were not in the historical data.
- **Not a replacement for live simulation.** Backtesting cannot account for market impact at scale. Paper trading performance does not guarantee live performance.

---

## Technical depth

For the mathematical rationale behind CPCV, DSR, and the multiple comparisons problem in strategy research: [docs/RESEARCH_PHILOSOPHY.md](docs/RESEARCH_PHILOSOPHY.md)

References: Bailey & López de Prado (2012), López de Prado (2018) *Advances in Financial Machine Learning*.

---

## Tests

824 passing. Run with:

```bash
python3 -m pytest
PYTHONPATH=src python3 -m aurora.cli.app demo run --latest-test-count 824
PYTHONPATH=src python3 -m aurora.cli.app reports safety-audit --no-fail-on-critical
```

Safety audit returns WARN. Expected findings: local simulation modules, safety phrase constants, audit pattern list, disabled broker adapter stubs. Not live trading indicators.