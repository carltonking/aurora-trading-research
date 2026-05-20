# AURORA — Autonomous Universe-Aware Research Optimization & Risk-managed Algorithm

AURORA Trading Research — v3.0.0

Most backtests are broken. Not in the sense that they use wrong data or bad assumptions — though that happens too — but in a more fundamental way: the methodology used to produce them systematically overstates performance, hides overfitting, and produces numbers that look precise while telling you almost nothing about what will happen next. Every open-source backtesting framework in common use has this problem. AURORA is a Python framework built around that reality.

It does not promise profitable strategies. It does not claim to eliminate overfitting. What it does is ship the tools that most frameworks leave as exercises for the reader: proper validation methodology, automatic leakage detection, statistical adjustment for multiple comparisons, and deterministic review gates that prevent optimistic interpretation from bypassing skeptical review. If you are building a trading strategy research workflow and you are not using these tools, your backtest results are probably wrong in a direction that favors your hypothesis.

## Why AURORA

### The k-fold cross-validation problem

Standard k-fold cross-validation is mathematically invalid for time series. When you shuffle data into folds, you train on future information and test on past information. The model sees returns from 2024 while predicting 2020. This is not a minor technical issue — it is a category error that invalidates every metric computed from shuffled splits. Nearly every open-source trading research framework uses k-fold or similar shuffled splits by default. AURORA uses Combinatorial Purged Cross-Validation (CPCV) instead, which respects temporal ordering and accounts for information leakage across train-test boundaries.

### The single-path problem

A backtest is one path through a distribution of possible outcomes. When you run one backtest, you see one number. That number reflects the specific sequence of market conditions that occurred in that period — and it tells you almost nothing about how the strategy would perform across the range of conditions that could have occurred. A strategy that looks strong in a single backtest may simply have been lucky with respect to regime. AURORA generates distributions of performance metrics across combinatorial train-test paths, so you can see whether your strategy is robust or regime-dependent.

### The selection bias problem

When you test 20 strategy variants and report the best one, you are not reporting a strategy — you are reporting the outcome of a selection process. The best of 20 random strategies will look better than any individual one, not because the strategy is good, but because selection amplifies noise. Naive Sharpe ratios do not account for this. The Deflated Sharpe Ratio (DSR) adjusts for the number of trials and the search space, so a Sharpe of 1.5 achieved by testing 100 variants means something very different from a Sharpe of 1.5 achieved with a single pre-specified strategy.

### The leakage problem

Lookahead bias is easy to introduce and hard to catch. A `.shift(-5)` in feature code looks innocuous. Normalizing over a window that includes the current bar leaks information. A label built from same-day returns uses information that would not be available at decision time. Most frameworks offer no automated detection. AURORA runs static AST analysis on feature code before every backtest, supplemented by runtime correlation testing that checks whether features are statistically independent of future label values. Compromised features are blocked from use.

## Core Methodology

AURORA implements four methodological components that address the problems above. See [docs/RESEARCH_PHILOSOPHY.md](docs/RESEARCH_PHILOSOPHY.md) for a detailed treatment.

**Combinatorial Purged Cross-Validation (CPCV).** Standard cross-validation shuffles time series data, training on the future and testing on the past. CPCV partitions the historical timeline into train and test sets while enforcing a purge buffer that prevents information from leaking across the boundary at decision time. Instead of one train-test split, it generates multiple combinatorial paths through time, producing a distribution of performance metrics rather than a single number. A strategy that passes CPCV across many paths is demonstrating robustness to different market regimes; a strategy that succeeds in one backtest and fails in the others is demonstrating sensitivity to the specific path.

**Deflated Sharpe Ratio (DSR).** The Sharpe ratio is a summary statistic computed from a single backtest. When you have run multiple strategy variants, multiple hyperparameter searches, or multiple feature combinations, the best Sharpe you observe is a maximum over a distribution of trials. The maximum is biased upward, and the bias grows with the number of trials. DSR deflates the observed Sharpe by an amount that accounts for the number of trials and the variance of the metric distribution, producing a probability-adjusted estimate that is comparable across different research programs. A DSR below zero indicates the strategy likely has no edge after accounting for the search process.

**Automated Leakage Detection.** AURORA runs two leakage checks before every backtest. The static analyzer performs AST-level scanning of feature code, detecting common lookahead patterns such as negative shifts. The runtime analyzer computes correlations between each feature and future label values at multiple horizons, flagging features with statistically significant forward correlations. A verdict of COMPROMISED blocks the research run. A verdict of SUSPECT adds a warning to the manifest. A verdict of CLEAN is recorded with no blocking action. No framework can catch all forms of leakage, but AURORA catches the most common ones automatically.

**Strategy Candidate Review Board.** Optimism is a known source of bias in strategy research. Researchers who believe in their hypothesis tend to interpret ambiguous results favorably. AURORA's Review Board applies deterministic rule-based evaluation to research artifacts — no human judgment, no narrative override. A strategy that meets quantitative thresholds across multiple metrics, walk-forward validation, and leakage checks receives APPROVED_FOR_PAPER_SIMULATION status. A strategy that fails any gate receives NEETS_MORE_RESEARCH or REJECTED. The board does not make trading decisions. It makes documentation decisions.

## Installation

```bash
git clone <your-repo-url>
cd aurora-trading-research
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
cp .env.example .env
```

Do not commit API keys or secrets. The codebase uses environment variables only.

## Testing

```bash
python3 -m pytest
```

Current test count: 824 passed, 6 skipped.

## CLI Usage

```bash
aurora status
aurora validate-config --config config/settings.example.yaml
aurora dashboard
```

## Data Layer

The primary data source is `yfinance`. A disabled LSEG Workspace adapter scaffold exists for future optional integration. Downloaded bars are normalized into AURORA's standard OHLCV schema. Data quality checks run before research workflows to catch missing fields, duplicate rows, invalid prices, suspicious volume, and large close-to-close moves.

```bash
aurora data health
aurora data download --symbols AAPL,MSFT --start 2020-01-01
aurora data quality --cache-key <cache-key>
```

## Feature Engineering

Features are calculated per symbol from normalized OHLCV data. The initial set includes returns, log returns, moving averages, rolling volatility, RSI, MACD, ATR, drawdown, distance from moving averages, rolling highs/lows, and volume change. Metadata — symbols, source, row count, feature names, configuration hash — is tracked for reproducibility.

```bash
aurora features build --cache-key <market-data-cache-key>
aurora features build --cache-key <market-data-cache-key> --dropna
```

## Model Training

Models are trained on research artifacts only. Labels are based on forward returns. Train/test splits are chronological to prevent lookahead leakage in evaluation. Artifacts are stored in a local registry with model files and metadata. This layer does not place trades or connect to broker execution.

```bash
aurora models train --features-key <features-cache-key>
aurora models list
aurora models predict --features-key <features-cache-key> --model-id <model-id>
```

## Strategies

Strategies are signal generators that produce long/flat positions. They do not connect to broker execution. Configs are validated to disallow shorting, margin, and oversized positions. The initial implementations are ML signal, moving average crossover, and momentum strategies.

```bash
aurora strategies validate --config-path examples/strategies/ml_signal_example.yaml
aurora strategies register --config-path examples/strategies/ml_signal_example.yaml
aurora strategies list
aurora strategies signal --strategy-id ml_signal_example --input-key <prediction-cache-key>
```

### Strategy Prompt Lab

A deterministic rule-based natural-language strategy builder. Converts plain-English prompts into validated strategy config drafts. It does not call external LLMs, generate executable code, place trades, or connect to brokers. High-risk requests — shorting, margin, options, leverage, HFT, live trading — are ignored and reported.

```bash
aurora strategies prompt --prompt "Create a conservative 20 and 50 day MA crossover for SPY"
```

## Research Runs

A local research cycle: market data, feature generation, strategy signals, backtesting, validation, and report. Artifacts are written to `data/research_runs/<run_id>/`. The default data mode is `cache_only`, which never downloads data. Use `download_if_missing` only when you want yfinance to fetch missing data.

Each run writes `manifest.json` with artifact paths, metrics, diagnostics, warnings, and safety flags. Safety flags document that no orders were placed, no broker was used, no ledger was written, and no external LLM was called.

```bash
aurora research run --strategy-id momentum_example --symbols SPY,QQQ --start-date 2020-01-01 --data-mode cache_only
```

## Review Board

Consumes `manifest.json`, `backtest.json`, `diagnostics.json`, and `report.md`. Outputs `review.json` with status: REJECTED, NEEDS_MORE_RESEARCH, or APPROVED_FOR_PAPER_SIMULATION. This is not live-trading approval. The board does not trade or call brokers.

```bash
aurora review run --run-dir data/research_runs/<run_id>
```

## Paper Simulation Readiness

Consumes `manifest.json`, `review.json`, and optional `backtest.json` and `diagnostics.json`. Outputs `paper_sim_readiness.json`: BLOCKED, NEEDS_MORE_RESEARCH, or READY_FOR_PAPER_SIMULATION. Does not trade or call brokers.

```bash
aurora readiness paper-sim --run-dir data/research_runs/<run_id>
```

## Paper Simulation Plan

Consumes `manifest.json`, `review.json`, and `paper_sim_readiness.json`. Outputs `paper_sim_plan.json`: BLOCKED or PLAN_READY. All paper simulation work is local-only.

```bash
aurora readiness paper-sim-plan --run-dir data/research_runs/<run_id>
```

## Backtesting

A transparent long-only backtester consuming signal data with configurable slippage, commission, and position sizing. No margin, no shorting. Research-only — does not place orders or connect to brokers.

```bash
aurora backtest run --signals-key <signals-cache-key>
```

## Validation

Walk-forward validation evaluates precomputed signals across chronological windows. Overfitting diagnostics warn about low trade count, unusually high metrics, return concentration, and failed validation. Research-only — does not promote strategies or execute trades.

```bash
aurora validation walk-forward --signals-key <signals-cache-key>
aurora validation diagnose-backtest --metrics-json <metrics.json>
```

## Risk Manager

A hard gate for execution paths. Evaluates trade candidates and returns auditable decisions: approved, rejected, reduced size, or kill switch triggered. Supports position sizing, exposure limits, loss limits, trade count limits, asset restrictions, no margin, no shorting, trade cooldowns, and kill switch. In this version it evaluates candidates only and does not place orders.

```bash
aurora risk check --symbol AAPL --side buy --quantity 10 --price 100
```

## Simulation and Paper Execution

The simulation broker is local-only. Every candidate passes the risk manager before any simulated fill. Approved and reduced-size candidates are filled locally; rejected and kill-switch decisions are logged without execution.

Paper ledger stores orders, risk decisions, account state, and positions as local JSON/JSONL files. Does not connect to Alpaca, use real API keys, or place real orders.

```bash
aurora execution simulate --symbol AAPL --side buy --quantity 10 --price 100
aurora execution account
```

Paper simulation from an approved plan submits every candidate through the RiskManager gate. Does not place real orders or write to global ledger paths.

```bash
aurora execution paper-sim-from-plan --run-dir data/research_runs/<run_id> --dry-run
aurora execution paper-sim-from-plan --run-dir data/research_runs/<run_id> --max-candidates 25
aurora execution review-paper-sim --run-dir data/research_runs/<run_id>
```

## Reporting

Local JSON and Markdown reports from ledger and research artifacts. Artifact packets with SHA-256 hashes. Project status snapshots. Safety boundary audits.

```bash
aurora reports daily --output-json data/reports/daily_summary.json
aurora reports daily --output-md data/reports/daily_summary.md
aurora reports packet --run-dir data/research_runs/<run_id> --create-zip
aurora reports status --latest-test-count 824
aurora reports safety-audit
```

## Demo

One-command local demo using deterministic synthetic OHLCV data. Runs the full research artifact workflow in `cache_only` mode. Does not call yfinance, brokers, external APIs, or external LLMs.

```bash
aurora demo run --latest-test-count 824
```

## Dashboard

Local Streamlit dashboard for inspecting cache files, model artifacts, strategy registry, backtest outputs, risk decisions, ledger state, and reports. Includes Guided Workflow and Demo Workflow tabs. Reads local files only, does not connect to Alpaca, does not place orders.

```bash
streamlit run src/aurora/dashboard/streamlit_app.py
```

## TUI

A terminal UI with 10 screens covering data exploration, strategy building, backtesting, paper trading, optimizer, readiness report, export, scheduler, settings, and logs.

```bash
aurora tui
```

## Roadmap

1. Project scaffold and safe defaults.
2. Configuration validation and schema hardening.
3. yfinance data adapter with normalization and quality checks.
4. Strategy registry and feature generation primitives.
5. Backtesting and walk-forward validation.
6. Risk manager integration and reporting.
7. Streamlit research dashboard.
8. Strategy Prompt Lab.
9. Leakage detection and DSR metrics.
10. CPCV validation.
11. Strategy Review Board and readiness gates.
12. Paper simulation workflow.
13. Adaptive optimizer.
14. LSEG and Alpaca paper adapter scaffolding.

---

> **Disclaimer:** AURORA is for research and educational use only. It is paper-trading-first and does not support live trading. It does not provide financial advice. Backtest and research results are not profitability guarantees. Past performance does not guarantee future results. Do not commit real API keys or secrets.