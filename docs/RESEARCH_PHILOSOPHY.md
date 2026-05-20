# Research Philosophy

This document explains the methodological choices behind AURORA. It is not a marketing document — it is a technical rationale. If you are evaluating whether to trust AURORA's approach, this is where you should look.

The central argument is simple: most algorithmic trading research produces results that are overfit to historical data, biased by methodological choices the researcher did not realize were consequential, and presented with a precision that the underlying data does not support. AURORA is built around this premise, not around the premise that profitable strategies are achievable.

---

## The Standard Backtest Is a Lie

Not always, and not intentionally. But the standard backtest — run one strategy against one historical period, report one Sharpe ratio — is methodologically inadequate in ways that almost always make the reported number look better than the strategy deserves.

### The multiple comparisons problem

Suppose you have no edge whatsoever. You are testing completely random strategies. If you test 50 of them against historical data, the best one will look good. That is not a coincidence — it is mathematics. The maximum of 50 random variables is systematically above the mean of any individual variable. You are not finding a good strategy; you are finding the luckiest failure.

This is the multiple comparisons problem, and it applies to every research workflow that tests multiple strategy variants, multiple feature sets, multiple hyperparameter configurations, or multiple lookback windows and then reports the best result. The act of selection introduces upward bias into every reported metric.

The bias is not small. In a research program testing 100 strategy variants, the best-performing variant will have an expected Sharpe roughly 2.5 times higher than the average Sharpe of the underlying true distribution — even if none of the variants have any actual edge. A Sharpe of 2.0 from a 100-variant search is not evidence of skill; it is the expected outcome of selection among noise.

This is why López de Prado (2018) argues that the standard Sharpe ratio is essentially uninformative after any nontrivial search process: it describes what happened in one realized path, not whether the underlying strategy has genuine predictive power.

### Why one path through time is not enough

A single backtest is one sample from a distribution of possible outcomes. The outcome depends on which market regimes occurred in the chosen period. A strategy that performs well in a low-volatility trending market may perform poorly in a high-volatility mean-reverting one. The single backtest tells you what happened — it does not tell you how sensitive the result is to the specific path that history took.

When you look at a backtest from 2015 to 2023, you are looking at one realization of a stochastic process. The strategy may have worked because the period was favorable, not because the strategy is robust. A methodology that cannot distinguish between these two explanations is not a research methodology — it is a storytelling tool.

---

## Deflated Sharpe Ratio

The Deflated Sharpe Ratio (DSR), introduced by Bailey and López de Prado (2012), adjusts the observed Sharpe to account for the number of trials and the variance of the Sharpe distribution across the search space.

The intuition: if you run 100 trials, the best observed Sharpe is a maximum of 100 draws from a distribution. That maximum is systematically above the true mean of the underlying distribution by an amount that depends on the number of trials and the variance. DSR deflates the observed Sharpe by the amount you would expect from this selection process.

The formula in outline:

```
DSR = (SR_observed - p) / VF
```

Where `p` is the expected maximum of `n` independent draws from a normal distribution with mean 0 and variance 1, and `VF` is a variance inflation factor that accounts for the cross-correlation of the strategy variants being compared.

In plain terms: a DSR above zero means the strategy likely has positive edge after accounting for the search process. A DSR below zero means the strategy likely has no edge — the observed Sharpe was produced by selection among noise. A DSR near zero is the most common outcome for genuinely edge-free strategies after any nontrivial search.

This is the right metric for comparing research programs with different numbers of trials. A Sharpe of 1.2 from a single pre-specified strategy is meaningful. A Sharpe of 1.2 from a 200-variant search is approximately meaningless without DSR adjustment.

AURORA computes DSR as part of research run diagnostics, so that reported performance can be evaluated in the context of the search process that produced it.

---

## Combinatorial Purged Cross-Validation

Standard k-fold cross-validation randomizes time series data, which produces train-test leakage: the model trains on future returns and tests on past returns. This is not a minor technical problem — it is a category error that invalidates every metric computed from the results.

CPCV addresses this by partitioning the timeline into embargo-free train/test windows while maintaining temporal ordering. It adds two constraints:

1. **Purging:** A buffer zone between the training set and test set prevents information from leaking across the boundary at the time of the trading decision. Trades near the boundary are excluded from both sets.

2. **Combinatorial enumeration:** Instead of one train-test split, CPCV enumerates multiple non-overlapping test sets, producing a distribution of performance metrics across paths. A strategy that performs consistently across multiple paths is demonstrating robustness to different temporal regimes; a strategy that succeeds in one path and fails in others is demonstrating sensitivity to the specific path.

The number of combinatorial paths grows quickly. With 12 temporal blocks, the number of unique test set combinations is large enough to characterize the performance distribution meaningfully. AURORA implements CPCV in its walk-forward validation layer.

The key insight is that the distribution of performance metrics across paths is more informative than any single path metric. If your strategy's Sharpe ratios across CPCV paths have a mean of 1.2 and a standard deviation of 0.8, you know something different from knowing that one backtest produced a Sharpe of 1.5. The single number hides the variance; the distribution reveals it.

---

## Leakage Taxonomy

Lookahead bias enters a financial ML pipeline through four main channels. Each is common, often subtle, and rarely caught by default by research frameworks.

### Label leakage

The label is constructed using information that would not be available at prediction time. The most common form is using same-day returns to construct forward-return labels: if you train a model to predict 5-day forward returns, those returns are in the historical bar for the current day. A model trained on this label has access to information that would not exist until the close of the prediction day. The fix is to shift labels by one bar, so a prediction for day `t` is trained on returns from `t+1` to `t+N`, all of which are in the future relative to the prediction point.

### Normalization leakage

Technical indicators and statistical features often involve rolling windows — z-score normalization, moving averages, standard deviation bands. If the rolling window extends to the current bar, it incorporates information from the current bar into the feature value. A model that uses this feature at the open of day `t` may have access to partial information from day `t`'s price movement. The fix is to ensure all rolling window computations are lagged by at least one bar relative to the prediction horizon.

### Feature leakage

Features are constructed using future information. The canonical example is a feature that uses a negative shift: `df['feature'] = df['price'].shift(-5)` — this loads the price from 5 bars in the future. Less obvious examples include features built from forward-filled data, features that use data from multiple timeframes without accounting for the decision time, or features computed on a non-lagged basis after a non-lagged label. Static AST analysis catches the obvious cases. Runtime correlation testing catches cases where future information enters through less direct paths.

### Temporal leakage

The training set includes data from after the test set period — a variant of the cross-validation leakage problem. This can happen through configuration errors in train/test splits, through information leakage in feature construction pipelines, or through data snooping in hyperparameter optimization. CPCV addresses this at the validation level. Static checking of feature code addresses it at the source level.

AURORA's leakage detector catches the first and third forms automatically. The second form requires care in feature construction — AURORA's feature layer enforces lagging by default, but it cannot prevent all misconfigurations. The fourth form is addressed through CPCV and through deterministic artifact management.

---

## The Honest Researcher's Checklist

Before you trust any backtest result — from AURORA or any other framework — you should be able to answer these questions:

- **How many strategy variants, feature sets, hyperparameter configurations, or lookback windows did you test?** If the answer is more than one, the best result is a maximum over a distribution and the naive Sharpe is biased upward. Use DSR.
- **What was the validation methodology?** If the answer involves shuffled splits or k-fold CV on time series data, the results are invalid. Use CPCV.
- **Did you check for lookahead bias in your features?** If the answer is "I think so," run the leakage detector. AST analysis finds common patterns automatically.
- **What is the distribution of performance across validation paths?** If you only have one number, you only know one outcome. Run CPCV to see the distribution.
- **What would a strategy with no actual edge look like on this evaluation?** If you do not know, the evaluation methodology cannot distinguish signal from noise.

---

## What AURORA Cannot Do

AURORA addresses a specific set of methodological problems in trading strategy research. It does not address the full set of ways that research can go wrong, and it is worth being explicit about the limits.

**AURORA does not guarantee profitable strategies.** It helps you evaluate whether your backtest results are methodologically sound. A methodologically sound backtest can still come from a strategy with no real edge. The tools AURORA provides — CPCV, DSR, leakage detection, review gates — help you avoid fooling yourself. They do not guarantee that what you find is real.

**Paper trading performance does not guarantee live performance.** Execution in a paper account differs from live execution in latency, fill quality, market impact, and psychological conditions. A strategy that performs well in paper simulation may perform differently in live markets for reasons that have nothing to do with the strategy's predictive power.

**CPCV reduces but does not eliminate overfitting risk.** CPCV produces a distribution of performance metrics across temporal paths. If your strategy is overfit to the specific historical period in your dataset — not just to the specific train-test splits — CPCV will not detect it. The validation is only as good as the historical data is representative of future conditions.

**The leakage detector catches common patterns but cannot catch all forms of leakage.** Static AST analysis catches `shift(-N)` and similar obvious patterns. Runtime correlation testing catches features that are statistically correlated with future label values. Subtle forms of leakage that do not produce detectable correlations, or that arise from the interaction of multiple features, may not be caught. Leakage detection is a necessary but not sufficient condition for methodological rigor.

**No backtesting framework can account for market impact at scale.** Backtesting assumes that your trades do not move the market. In live execution, especially with larger position sizes or less liquid instruments, your trades move prices against you. A backtest that shows strong performance at a given position size may show poor performance at a size that actually matters. This is not a modeling problem that can be solved in a backtesting framework — it requires live simulation with realistic position sizing.

**AURORA does not make investment decisions.** Every execution path goes through the RiskManager. Every paper simulation requires a review board decision. AURORA produces research artifacts — metrics, diagnostics, reports, proposals. The human researcher makes the decision about whether to act on any of them.

---

## References

- Bailey, D. H., & López de Prado, M. M. (2012). The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting, and Non-Normality. *Journal of Portfolio Management*, 39(4), 112–119.
- López de Prado, M. M. (2018). *Advances in Financial Machine Learning*. John Wiley & Sons. Chapters 4, 5, 7, and 12.