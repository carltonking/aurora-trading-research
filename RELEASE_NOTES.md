# AURORA Release Notes

## v3.0.0 — The Methodology Release

This is the version where AURORA becomes something different from most algorithmic trading research tools: a framework that enforces methodological rigor as a default, not as an option.

The problem this release solves is specific and well-documented in the academic literature, but almost entirely absent from open-source tooling: most backtest results are meaningless as evidence of strategy quality because the methodology used to produce them systematically overstates performance. The overstatement comes from three sources that are individually easy to miss and collectively devastating: shuffled cross-validation on time series data, selection bias from testing multiple strategy variants, and lookahead bias in feature construction. Every one of these is well-understood. None of them are defaults in common open-source frameworks.

AURORA v3.0.0 addresses all three.

### What changed

Combinatorial Purged Cross-Validation (CPCV) replaces single-path backtesting as the primary validation method. Instead of partitioning data into a single training set and a single test set, CPCV generates a combinatorial set of non-overlapping test paths with purge buffers between train and test boundaries. This produces a distribution of performance metrics rather than a single number — and the distribution tells you something the single number cannot, which is whether your strategy's performance is robust across market regimes or sensitive to the specific path that history took.

Deflated Sharpe Ratio (DSR) adjusts the observed Sharpe ratio for selection bias. When you test 50 strategy variants and report the best one, the best is not a property of the strategy — it is a property of the selection process. The maximum of 50 draws from a normal distribution is systematically above the mean, and the upward bias grows with the number of trials. DSR deflates the observed Sharpe by the amount you would expect from the search process, producing a probability-adjusted estimate. A DSR below zero means the strategy likely has no edge after accounting for the number of trials you ran.

Automated Feature Leakage Detection runs before every backtest. A static AST analyzer scans feature code for lookahead patterns — the most common is `shift(-N)`, which looks forward in time. A runtime analyzer tests whether each feature is statistically correlated with future label values beyond the prediction horizon. A verdict of COMPROMISED blocks the research run. A verdict of CLEAN is recorded in the manifest. The detection is not exhaustive — no automated system can catch every form of leakage — but it catches the most common patterns automatically, which prevents the most frequent class of errors from proceeding to backtesting.

The Strategy Candidate Review Board enforces CPCV and DSR thresholds as deterministic gates. A strategy that produces a good Sharpe in a single backtest but fails across CPCV paths, or has a DSR below zero, receives NEEDS_MORE_RESEARCH status regardless of the naive metric. This is not a recommendation engine — it is a documentation system that records what the evidence actually supports.

### Who this is built for

AURORA is built for researchers who understand that backtesting without proper validation methodology produces numbers that look precise while telling you almost nothing. It is not a platform for generating impressive-looking backtests quickly. It is a framework for evaluating whether a strategy has genuine edge after accounting for the ways that research can be wrong in a direction that favors the hypothesis.

If you are evaluating a trading strategy research program, AURORA will not make your results look better than they are. What it will do is make it harder to accidentally mistake noise for signal, and easier to document what your evidence actually supports.

### What this is not

AURORA is a research tool. It does not place trades, does not connect to live broker execution, and does not guarantee profitable outcomes. Paper trading performance does not predict live performance. The methodology in this release is sound relative to the alternatives, but no backtesting methodology can account for market impact at scale, behavioral factors in live execution, or regime shifts that were not represented in the historical data.

The tools AURORA provides help you avoid fooling yourself. They do not guarantee that what you find is real.

### Local verification

```bash
python3 -m pytest
PYTHONPATH=src python3 -m aurora.cli.app demo run --output-root data/demo --latest-test-count 824
PYTHONPATH=src python3 -m aurora.cli.app reports safety-audit --no-fail-on-critical
```

Current test count: 824 passed, 6 skipped.

The safety audit returns WARN. This is expected from intentional local simulation modules, safety phrase constants, and the audit pattern list itself. These are not live trading indicators.

---

For the technical rationale behind CPCV, DSR, and leakage detection: [docs/RESEARCH_PHILOSOPHY.md](docs/RESEARCH_PHILOSOPHY.md)

---

## v2.2.1 - 2026-05-20

### Terminal User Interface (TUI)

- Textual-based terminal UI with 10 screens covering data exploration, strategy building, backtesting, paper trading, optimizer, readiness report, export, scheduler, settings, and logs
- Keyboard shortcuts (F1-F11) for navigation across all screens
- Custom widgets: MetricCard, SparklineChart, DisclaimerFooter
- Mandatory disclaimer footer on all screens

### Web UI Updates

- Export Screen for strategy bundle generation with download
- Scheduler Screen for YAML schedule editing, validation, and start/stop control
- Deployment Checklist Screen for running checklist, viewing results, and exporting JSON

### Interface Parity

- All 11 primary features available in CLI, Web UI, and TUI
- Interface comparison table in AGENTS.md

### Testing

- 787 tests passed
- TUI screen tests and Web UI function tests added

### Safety

- All existing safety boundaries maintained
- No live trading, no broker execution
- All interfaces include mandatory disclaimers

## v2.2.0 - 2026-05-20

### Research & Validation

- Monte Carlo simulation for backtest robustness via resampled paths
- Stress testing with built-in scenarios: 2008 crash, 2020 covid, rate shock
- Sensitivity analysis for parameter robustness evaluation
- Walk-forward validation enhancements
- Multi-asset and universe support for portfolio-level backtesting
- Intraday data support for sub-daily intervals

### Paper Trading Realism

- Real-time streaming for paper data feeds
- Slippage and commission models for realistic fill simulation
- Order queue and latency modeling
- Paper trading dashboard for visual monitoring

### Strategy Development

- Grid archetype for grid-based trading strategies
- Pairs archetype for pairs trading strategies
- DCA archetype for dollar-cost averaging strategies
- Ensemble strategies for multi-strategy combination
- Genetic optimizer and Bayesian optimizer for evolutionary and probabilistic parameter search
- Walk-forward optimizer for time-series-aware optimization

### Risk & Portfolio

- Portfolio RiskManager for multi-position risk controls
- Dynamic position sizing: Kelly criterion, fixed fraction, volatility-adjusted
- Kill-switch triggers for emergency shutdown conditions

### Reporting

- Equity curve plotting for visual performance charts
- PDF readiness report for exportable documentation
- Diffable artifacts for version tracking of results

### Infrastructure

- Persistent config files (.aurora.yml) for project configuration
- Task scheduler for periodic research automation
- Local web UI via Streamlit dashboard
- Alternative data sources: FRED, SEC EDGAR, News API
- Plugin system for extensible architecture
- Strategy sandbox via AST-based code validation
- Deployment checklist for advisory readiness verification

### Safety

- Sandbox validates external strategy code via AST scanning for dangerous imports and calls
- Plugin secret detection rejects hardcoded API keys and tokens in plugin files
- Deployment checklist is advisory only, never grants live trading permission
- Kill-switch triggers add runtime safety gates
- All modules follow existing safety boundaries: no live trading, no real broker execution

## v2.1.0 - 2026-05-19

### Phase 2B: LSEG Client Boundary

- Optional dependency `lseg` for market data
- RealLSEGClient fails closed when SDK is not installed or credentials are missing
- Secrets never exposed in repr, str, or health_check messages
- yfinance remains the default data source

### Phase 3A: Alpaca Paper-Only Adapter

- AlpacaPaperBrokerProtocol with paper-only methods
- RealAlpacaPaperClient blocks live trading and raises AlpacaLiveTradingError
- FakeAlpacaPaperClient for tests and dry-run (default)
- Default disabled, opt-in via environment variables

### Phase 3B: Paper Execution Path

- PaperExecutor gates all orders through RiskManager
- PaperExecutionRequest/Result dataclasses for audit trail
- Ledger records all decisions (APPROVED/REJECTED/KILL_SWITCH) to JSONL
- Never calls broker without RiskManager approval

### Phase 4A: Adaptive Strategy Optimizer

- AdaptiveOptimizer reads research artifacts (manifest, backtest, diagnostics, review)
- Deterministic proposals: REJECTED, NEEDS_MORE_RESEARCH, PROPOSED_FOR_REVIEW
- Simple rules: Sharpe < 0.5, drawdown > 0.3, win_rate < 0.4 trigger NEEDS_MORE_RESEARCH
- Never claims profitability, research-only
- CLI: `aurora optimize analyze`

### Phase 5A: Paper Performance Analysis

- PaperMetrics dataclass and PaperPerformanceAnalyzer class
- Computes metrics from execution ledger (APPROVED trades only)
- Placeholder P&L estimation (real fill data TBD)
- CLI: `aurora paper performance --strategy <name> --output-dir`
- Required disclaimer: "Past paper performance does not guarantee future results"

### Phase 5B: Adaptive Optimizer with Paper Metrics

- AdaptiveOptimizer extended with paper_metrics_path parameter
- Analyzes paper win_rate < 0.35 or max_drawdown > 0.4 as NEEDS_MORE_RESEARCH
- Paper declining (Sharpe < backtest * 0.6) triggers conservative parameter adjustments
- Rationale includes: "paper trading results indicate alignment with historical research; no guarantee of future performance"
- CLI: `aurora optimize analyze --strategy <name> --paper-metrics <path>`

### Phase 5C: Config-Driven Strategy Builder

- Strategy archetypes: TrendFollowingStrategy, MeanReversionStrategy, BreakoutStrategy
- StrategyBuilder parses JSON/YAML config, instantiates archetype with parameters
- generate_code() produces exportable Python class
- CLI: `aurora strategy build --config <path> --output-strategy-file <path>`

### Phase 5D: Comprehensive Readiness Report

- ReadinessReport and ReadinessReportGenerator aggregate backtest, walk-forward, paper metrics, and optimization proposals
- Assessment heuristics: weak paper → "elevated risk", NEEDS_MORE_RESEARCH → "further research", all thresholds pass → "All research gates passed"
- Mandatory disclaimer about research-only, no guarantees
- CLI: `aurora report readiness --strategy <name> --output <path>`

### Phase 5E: Strategy Export Bundle

- StrategyExporter creates ZIP bundles with strategy code, model, feature config, readiness report, backtest/diagnostics
- Secret detection scans for API keys, passwords, tokens; allows os.getenv() placeholders
- Manifest includes AURORA version and disclaimer
- CLI: `aurora export strategy --strategy <name> --output <path.zip>`

### Safety Boundaries (All Phases)

- No live trading — all execution is paper/simulation only
- No real broker execution — local simulation only
- RiskManager gate — every candidate evaluated before any action
- No secrets in code or logs — environment variables only, repr masking
- No profitability claims — research results are not guarantees

Latest verified test result: 824 passed.
Safety audit status: WARN (45 findings, expected patterns).