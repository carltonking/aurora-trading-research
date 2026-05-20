# AURORA Trading Research

**AURORA** stands for **Autonomous Universe-aware Research Optimization & Risk-managed Algorithm**.

AURORA Trading Research is a research-first, paper-trading-first Python platform for generating, validating, and monitoring ML-assisted strategy candidates with strict risk controls. The project is designed to be modular, testable, and suitable for public GitHub development.

> Disclaimer: AURORA is for research and educational use. It is paper-trading-first, and v1 does not support live trading. It does not provide financial advice, investment advice, or recommendations to buy, sell, or hold any financial instrument. Backtest and research results are not profitability guarantees. Do not commit real API keys or secrets.

## Current Scope

Version 1 is research-only. It supports local market data research, feature generation, model experiments, signal generation, backtesting, validation, review gates, artifact reporting, safety audits, and local-only simulation tooling. It does not support live trading, real broker execution, real order placement, or production deployment.

See [docs/SAFETY.md](docs/SAFETY.md) for the project safety posture.
See [docs/PAPER_BROKER_INTEGRATION.md](docs/PAPER_BROKER_INTEGRATION.md) for design-only requirements for any future paper broker integration.

## Current v1 Release Candidate Status

AURORA v1 is GitHub-ready as a research-first, paper-trading-first platform. The release-candidate audit found no blocking issues.

- Latest verified test result: `293 passed`.
- Safety audit status: `WARN`. The warnings are expected from intentional local simulation/ledger modules, static safety phrase patterns, Prompt Lab unsupported-request constants, and the audit pattern list itself.
- Ruff was not installed in the audit environment; running the configured Ruff checks locally is an optional follow-up.
- v1 does not support live trading, does not require real API keys, and does not make profitability claims.
- Any future broker/API integration must remain explicitly paper-trading-first and pass safety, review, readiness, and risk gates.

## Current v2 Release Candidate Status

AURORA v2 remains local-first and paper-trading-first. The current v2 feature set adds local artifact workflow polish, local paper simulation from approved plans, paper simulation review, and disabled broker adapter scaffolding only.

- Latest verified test result: `293 passed`.
- Safety audit status: `WARN`. The warnings are expected from intentional local simulation/ledger modules, safety phrase constants, Prompt Lab unsupported-request constants, audit pattern definitions, and disabled broker adapter stub `submit_order` interfaces.
- v2 includes local paper simulation from approved plans through the existing local simulation path.
- v2 includes disabled broker adapter scaffolding only, not actual broker API integration.
- No live trading support exists.
- No Alpaca dependency, endpoint configuration, network broker call, real order placement, or real API key requirement exists.

### Completed v2 Layer Summary

- Artifact packet ZIP export.
- Guided Workflow dashboard.
- Deterministic local demo workflow.
- Local paper simulation from approved plan.
- Paper simulation review/audit.
- `paper_sim_review.json` packet/status integration.
- Paper broker integration safety design document.
- Disabled broker adapter interface/stub scaffolding.

## What's New in v2.2.0

AURORA v2.2.0 adds 27 new features across research, paper trading, strategy development, risk, reporting, and infrastructure:

### Research & Validation
- **Monte Carlo simulation**: Robustness testing via resampled paths
- **Stress testing**: Built-in scenarios (2008 crash, 2020 covid, rate shock)
- **Sensitivity analysis**: Parameter robustness evaluation
- **Walk-forward enhancements**: Improved validation methodology
- **Multi-asset/universe support**: Portfolio-level backtesting
- **Intraday data**: Sub-daily interval support

### Paper Trading Realism
- **Real-time streaming**: Live paper data feed
- **Slippage/commission models**: Realistic fill simulation
- **Order queue & latency**: Execution timing models
- **Paper trading dashboard**: Visual monitoring

### Strategy Development
- **Grid archetype**: Grid-based trading strategy
- **Pairs archetype**: Pairs trading strategy
- **DCA archetype**: Dollar-cost averaging strategy
- **Ensemble strategies**: Multi-strategy combining
- **Genetic optimizer**: Evolutionary parameter search
- **Bayesian optimizer**: Probabilistic optimization
- **Walk-forward optimizer**: Time-series validation optimizer

### Risk & Portfolio
- **Portfolio RiskManager**: Multi-position risk controls
- **Dynamic position sizing**: Kelly, fixed fraction, volatility-adjusted
- **Kill-switch triggers**: Emergency shutdown conditions

### Reporting
- **Equity curve plotting**: Visual performance charts
- **PDF readiness report**: Exportable documentation
- **Diffable artifacts**: Version tracking for results

### Infrastructure
- **Persistent config files**: `.aurora.yml` project configuration
- **Task scheduler**: Periodic research automation
- **Local web UI**: Streamlit dashboard
- **Alternative data sources**: FRED, SEC EDGAR, News API
- **Plugin system**: Extensible architecture
- **Strategy sandbox**: AST-based code validation
- **Deployment checklist**: Advisory readiness verification

### Safety Boundaries (Updated)
- Sandbox validates external strategy code via AST scanning
- Plugin secret detection rejects hardcoded API keys
- Deployment checklist is advisory only - never grants live trading permission
- Kill-switch triggers add runtime safety gates

- Latest verified test result: `787 passed`
- Safety audit status: `WARN (45 findings)`

## What's New in v2.2.1

### Terminal User Interface (TUI)
- **Textual-based TUI**: Full terminal UI with 10 screens
- **Keyboard navigation**: F1-Home, F2-Data, F3-Strategy, F4-Backtest, F5-Paper, F6-Optimize, F7-Readiness, F8-Export, F9-Scheduler, F10-Settings, F11-Logs
- **Custom widgets**: MetricCard, SparklineChart, DisclaimerFooter

### Web UI Updates
- **Export Screen**: Generate and download strategy export bundles
- **Scheduler Screen**: Edit schedule YAML, validate, start/stop scheduler
- **Deployment Checklist Screen**: Run checklist, view results, export JSON

### Interface Parity
- All 11 primary features available in CLI, Web UI, and TUI

## What's New in v2.1.0

AURORA v2.1.0 adds four new phase modules while maintaining all existing safety boundaries:

### Phase 2B: LSEG Client Boundary
- Optional `lseg` dependency for market data.
- `RealLSEGClient` fails closed when SDK missing or credentials absent.
- Configuration via environment variables: `LSEG_ENABLED`, `LSEG_APP_KEY`, `LSEG_USERNAME`, `LSEG_PASSWORD`.
- yfinance remains the default data source.

### Phase 3A: Alpaca Paper-Only Adapter
- `AlpacaPaperBrokerProtocol` with paper trading methods.
- `RealAlpacaPaperClient` blocks live trading - raises `AlpacaLiveTradingError`.
- `FakeAlpacaPaperClient` for tests/dry-run (default).
- Configuration via: `ALPACA_PAPER_ENABLED`, `ALPACA_PAPER_KEY`, `ALPACA_PAPER_SECRET`.

### Phase 3B: Paper Execution Path
- `PaperExecutor` gates ALL orders through `RiskManager`.
- `PaperExecutionRequest`/`PaperExecutionResult` for audit trail.
- Ledger records every decision (APPROVED/REJECTED/KILL_SWITCH).
- Never calls broker without RiskManager approval.

### Phase 4A: Adaptive Strategy Optimizer
- `AdaptiveOptimizer` reads research artifacts.
- Deterministic proposals: REJECTED, NEEDS_MORE_RESEARCH, PROPOSED_FOR_REVIEW.
- Simple rules: Sharpe < 0.5, drawdown > 0.3, win_rate < 0.4 trigger NEEDS_MORE_RESEARCH.
- CLI: `aurora optimize analyze --strategy <name> --artifact-dir <path>`
- Never claims profitability, research-only.

### Phase 5A: Paper Performance Analysis
- `PaperMetrics` dataclass and `PaperPerformanceAnalyzer` class.
- Computes metrics from execution ledger (APPROVED trades only).
- Placeholder P&L estimation (real fill data TBD).
- CLI: `aurora paper performance --strategy <name> --output-dir`
- Required disclaimer: "Past paper performance does not guarantee future results."

### Phase 5B: Adaptive Optimizer with Paper Metrics
- `AdaptiveOptimizer` extended with `paper_metrics_path` parameter.
- Analyzes paper win_rate < 0.35 or max_drawdown > 0.4 → NEEDS_MORE_RESEARCH.
- Paper declining (Sharpe < backtest * 0.6) triggers conservative parameters.
- Rationale: "Paper trading results indicate alignment with historical research; no guarantee of future performance."
- CLI: `aurora optimize analyze --strategy <name> --paper-metrics <path>`

### Phase 5C: Config-Driven Strategy Builder
- Strategy archetypes: `TrendFollowingStrategy`, `MeanReversionStrategy`, `BreakoutStrategy` in `src/aurora/strategies/archetypes/`.
- `StrategyBuilder` parses JSON/YAML config, instantiates archetype with parameters.
- `generate_code()` produces exportable Python class.
- CLI: `aurora strategy build --config <path> --output-strategy-file <path>`

### Phase 5D: Comprehensive Readiness Report
- `ReadinessReport` and `ReadinessReportGenerator` aggregate backtest, walk-forward, paper metrics, optimization proposals.
- Assessment heuristics: weak paper → "elevated risk", NEEDS_MORE_RESEARCH → "further research", all pass → "All research gates passed".
- Mandatory disclaimer about research-only, no guarantees.
- CLI: `aurora report readiness --strategy <name> --output <path>`

### Phase 5E: Strategy Export Bundle
- `StrategyExporter` creates ZIP bundles with strategy code, model, feature config, readiness report, backtest/diagnostics.
- Secret detection scans for API keys, passwords, tokens; allows `os.getenv()` placeholders.
- Manifest includes AURORA version and disclaimer.
- CLI: `aurora export strategy --strategy <name> --output <path.zip>`

### Safety Boundaries (All Phases)
- **No live trading** - all execution is paper/simulation only.
- **No real broker execution** - local simulation only.
- **RiskManager gate** - every candidate evaluated before any action.
- **No secrets in code/logs** - environment variables only, repr masking.
- **No profitability claims** - research results are not guarantees.

Latest verified test result: **395 passed**.
Safety audit status: **WARN** (37 findings, expected patterns).

## Release Artifacts

- [CHANGELOG.md](CHANGELOG.md)
- [RELEASE_NOTES.md](RELEASE_NOTES.md)
- [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md)
- [docs/SAFETY.md](docs/SAFETY.md)
- [docs/PAPER_BROKER_INTEGRATION.md](docs/PAPER_BROKER_INTEGRATION.md)

## Current Feature Overview

- Market data.
- Feature engineering.
- Model training and registry.
- Strategy registry and signal generation.
- Research-only backtesting.
- Validation and diagnostics.
- Risk manager hard gate.
- Local simulation broker and paper ledger.
- Reporting/dashboard MVP.
- Deterministic Strategy Prompt Lab.
- Local research run orchestration.
- Strategy Candidate Review Board.
- Paper Simulation Readiness Gate.
- Paper Simulation Plan.
- Research Artifact Packet Builder.
- Project Status Snapshot.
- Safety Boundary Audit.
- End-to-end local artifact workflow fixture test.
- Typer CLI and local Streamlit dashboard.
- Optional LSEG market data client (disabled by default).
- Alpaca paper-only broker adapter (disabled by default).
- Paper execution path with RiskManager gating.
- Adaptive strategy optimizer (research-only).
- Paper performance analysis.
- Adaptive optimizer with paper metrics feedback.
- Config-driven strategy builder with archetypes.
- Comprehensive readiness report generator.
- Strategy export bundle with secret detection.

## Safety Boundaries

- Research-first and paper-trading-first.
- No live trading.
- No real broker execution.
- No real order placement.
- No direct order placement from prompts.
- No external LLM/API calls.
- No real API keys in the repository.
- No profitability claims.
- All execution paths go through RiskManager.
- Alpaca live trading explicitly blocked.
- Optimizer never calls brokers.

## Future Adapter Plans

- LSEG Workspace adapter scaffolding exists (disabled/fail-closed by default); real LSEG client/credential integration is not implemented yet.
- Future Alpaca paper adapter only after additional review gates.
- Current Alpaca paper scaffolding is disabled, dry-run-only, and non-networked.
- No live trading support is implemented or approved.

## Future Paper Broker Integration Design

AURORA includes a design-only safety document for any future paper broker integration: [docs/PAPER_BROKER_INTEGRATION.md](docs/PAPER_BROKER_INTEGRATION.md).

No broker adapter is implemented by that document. Current local workflows do not require broker API keys. Any future broker-paper adapter must remain paper-only by default, require review/readiness/plan artifacts, require `RiskManager` approval for every candidate, and must not approve live trading.

## Broker Adapter Stubs

AURORA now includes disabled broker adapter interfaces for future paper integration work. The Alpaca paper adapter is a non-network stub: it adds no package dependency, defines no endpoints, reads no API keys, and does not place orders.

These stubs are disabled by default and dry-run-only. Future implementation work must follow [docs/PAPER_BROKER_INTEGRATION.md](docs/PAPER_BROKER_INTEGRATION.md), preserve `RiskManager` gating, and remain paper-only unless a separate safety design changes the project scope.

## Installation

```bash
git clone <your-repo-url>
cd aurora-trading-research
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

Copy the example environment file before local development:

```bash
cp .env.example .env
```

Do not commit real API keys or secrets.

## Tests

```bash
python3 -m pytest
```

## CLI Usage

```bash
aurora status
aurora validate-config --config config/settings.example.yaml
aurora dashboard
```

## Market Data Layer

The first implemented market data source is `yfinance`. LSEG Workspace adapter scaffolding exists (disabled by default) and is planned for later integration. Future Alpaca paper adapter only after additional review gates.

Downloaded bars are normalized into AURORA's standard OHLCV schema before use. Data quality checks run before research workflows to catch missing fields, duplicate rows, invalid prices, suspicious volume, and large close-to-close moves that may require review.

```bash
aurora data health
aurora data download --symbols AAPL,MSFT --start 2020-01-01
aurora data quality --cache-key <cache-key>
```

## Feature Engineering Layer

Features are generated from normalized OHLCV data and calculated per symbol to avoid cross-symbol leakage. The initial feature set includes returns, log returns, moving averages, rolling volatility, RSI, MACD, ATR, drawdown, distance from moving averages, rolling highs/lows, and volume change.

Feature metadata is tracked for reproducibility, including symbols, source, row count, feature count, feature names, and a deterministic configuration hash.

```bash
aurora features build --cache-key <market-data-cache-key>
aurora features build --cache-key <market-data-cache-key> --dropna
```

## Model Training Layer

AURORA currently includes a baseline supervised classifier for research workflows. Labels are based on forward returns, and train/test splits are chronological to reduce lookahead leakage in model evaluation.

Model artifacts are stored in a local registry under `data/models` with `model.pkl` and `metadata.json`. This layer is research-only and does not place trades or connect to broker execution.

```bash
aurora models train --features-key <features-cache-key>
aurora models list
aurora models predict --features-key <features-cache-key> --model-id <model-id>
```

## Strategy Layer

Strategies are research-only signal generators. They produce long/flat signals, not orders, and do not connect to broker execution.

Strategy configs are validated to disallow shorting, margin, and oversized positions in v1. Configs can be saved to a local registry under `data/strategies`, then used to generate cached signal outputs. The initial supported implementations are ML signal, moving average crossover, and momentum strategies.

```bash
aurora strategies validate --config-path examples/strategies/ml_signal_example.yaml
aurora strategies register --config-path examples/strategies/ml_signal_example.yaml
aurora strategies list
aurora strategies signal --strategy-id ml_signal_example --input-key <prediction-cache-key>
```

## Strategy Prompt Lab

The Strategy Prompt Lab is a deterministic rule-based natural-language strategy builder. It converts simple plain-English prompts into validated strategy config drafts only.

It does not call external LLMs, generate executable code, place trades, or connect to brokers. Unsupported high-risk requests such as shorting, margin, options, crypto, leverage, scalping, high-frequency trading, live trading, or real-money trading are ignored and reported. Generated configs must still be registered, signal-generated, backtested, and validated before any further research use.

```bash
aurora strategies prompt --prompt "Create a conservative 20 and 50 day moving average crossover strategy for SPY and QQQ"
```

## Research Runs

AURORA can orchestrate a local research cycle from existing components: market data, feature generation, strategy signals, research-only backtesting, diagnostics, and a Markdown report. Run artifacts are written under `data/research_runs/<run_id>/`.

Research runs are local and research-only. They do not place trades, create orders, call brokers, or connect to Alpaca. Generated metrics and reports are diagnostic outputs, not profitability claims.

The default data mode is `cache_only`, which never downloads market data and fails clearly if matching cached data is missing. Use `download_if_missing` only when you explicitly want the existing yfinance research data adapter to retrieve missing local data.

Each successful run writes `manifest.json` with artifact paths, metrics and diagnostics summaries, warnings, and safety flags. The manifest safety flags should show `placed_orders: false`, `used_broker: false`, `wrote_ledger: false`, and `external_llm_calls: false`.

```bash
aurora research run --strategy-id momentum_example --symbols SPY,QQQ --start-date 2020-01-01 --data-mode cache_only

aurora research run --strategy-id momentum_example --symbols SPY,QQQ --start-date 2020-01-01 --data-mode download_if_missing
```

## Strategy Candidate Review Board

The Strategy Candidate Review Board consumes completed research run artifacts such as `manifest.json`, `backtest.json`, `diagnostics.json`, and `report.md`. It applies deterministic local rules and writes a `review.json` decision artifact.

Possible statuses are `REJECTED`, `NEEDS_MORE_RESEARCH`, and `APPROVED_FOR_PAPER_SIMULATION`. This is not live-trading approval. The review board does not trade, place orders, call brokers, or approve live trading.

```bash
aurora review run --run-dir data/research_runs/<run_id>
```

## Paper Simulation Readiness Gate

The Paper Simulation Readiness Gate consumes `manifest.json`, `review.json`, and optional `backtest.json` and `diagnostics.json` from a completed research run. It applies deterministic artifact-only checks and writes `paper_sim_readiness.json`.

Possible statuses are `BLOCKED`, `NEEDS_MORE_RESEARCH`, and `READY_FOR_PAPER_SIMULATION`. Readiness is only for future local paper simulation. It does not trade, place orders, call brokers, or approve live trading.

```bash
aurora readiness paper-sim --run-dir data/research_runs/<run_id>
```

## Paper Simulation Plan

The Paper Simulation Plan consumes `manifest.json`, `review.json`, and `paper_sim_readiness.json` from a completed research run. It applies deterministic artifact-only planning rules and writes `paper_sim_plan.json`.

Possible statuses are `BLOCKED` and `PLAN_READY`. Plan readiness is only for future local paper simulation. It does not trade, place orders, call brokers, write ledgers, or approve live trading.

```bash
aurora readiness paper-sim-plan --run-dir data/research_runs/<run_id>
```

## Backtesting Layer

AURORA includes a simple transparent long-only backtester for research. The backtester consumes signal data, not raw strategy code, and simulates long/flat exposure with configurable slippage, commission, position sizing, no margin, and no shorting.

Backtesting is research-only and does not place orders or connect to broker execution.

```bash
aurora backtest run --signals-key <signals-cache-key>
```

## Validation Layer

Walk-forward validation evaluates precomputed signals across chronological windows. This helps test whether a signal set behaves consistently outside a single continuous backtest period.

Overfitting diagnostics warn about low trade count, unusually high metrics, return concentration, and failed validation. Validation is research-only and does not promote strategies or execute trades.

```bash
aurora validation walk-forward --signals-key <signals-cache-key>
aurora validation diagnose-backtest --metrics-json <metrics.json>
```

## Risk Manager

The risk manager is a hard gate for future execution paths. It evaluates trade candidates before any simulated or paper order workflow and returns an auditable decision: approved, rejected, reduced size, or kill switch triggered.

The current risk layer supports position sizing, total exposure limits, daily and weekly loss limits, trade count limits, asset restrictions, no margin, no shorting, trade cooldowns, and a kill switch. In this version it only evaluates candidates and does not place orders.

```bash
aurora risk check --symbol AAPL --side buy --quantity 10 --price 100
```

## Simulation Broker and Paper Ledger

The simulation broker is local-only. Every trade candidate passes through the risk manager before any simulated fill is created. Approved and reduced-size candidates are filled locally, while rejected and kill-switch decisions are recorded without execution.

The paper ledger stores orders, risk decisions, account state, and positions as local JSON/JSONL files under `data/ledger`. This does not connect to Alpaca, use real API keys, or place real orders.

```bash
aurora execution simulate --symbol AAPL --side buy --quantity 10 --price 100
aurora execution account
```

## Local Paper Simulation From Plan

AURORA can run local paper simulation from an existing research run only after the run has `paper_sim_readiness.json`, `paper_sim_plan.json`, and `signals.csv`. The command consumes those artifacts, requires the plan and readiness gate to be ready by default, and submits every simulated trade candidate through the `RiskManager` hard gate.

Simulation outputs are written under `<run_dir>/paper_simulation/` by default. This uses the local `SimulationBroker` and `PaperLedger` only. It does not place real orders, call brokers, write the global `data/ledger` path by default, or approve live trading.

```bash
aurora execution paper-sim-from-plan --run-dir data/research_runs/<run_id> --dry-run
aurora execution paper-sim-from-plan --run-dir data/research_runs/<run_id> --max-candidates 25
```

## Paper Simulation Review

AURORA can review local paper simulation artifacts after a plan-driven local simulation run. The review consumes `paper_simulation/simulation_manifest.json`, `orders.jsonl`, `risk_decisions.jsonl`, `account.json`, and `positions.json`, then writes `paper_simulation/paper_sim_review.json`.

The review summarizes orders, risk decisions, account state, and positions. It is artifact-only: it does not execute simulation, trade, place real orders, call brokers, write ledger files, or approve live trading.

```bash
aurora execution review-paper-sim --run-dir data/research_runs/<run_id>
```

## Reporting Layer

AURORA can generate local JSON and Markdown reports from ledger and research artifacts. The first report utility creates a daily summary from local account state, positions, orders, risk decisions, and optional backtest metrics. No external services are used.

```bash
aurora reports daily --output-json data/reports/daily_summary.json
aurora reports daily --output-md data/reports/daily_summary.md
```

## Research Artifact Packets

AURORA can build a local packet from completed research run artifacts. The packet builder writes `artifact_packet/packet_manifest.json`, can optionally copy known artifacts into the packet directory, can optionally create `artifact_packet.zip`, and computes SHA-256 hashes for auditability.

When present, packets also include the local paper simulation review artifact at `paper_simulation/paper_sim_review.json`.

Possible packet statuses are `COMPLETE`, `PARTIAL`, and `BLOCKED`. Packet building and ZIP export only read and package local research artifacts. They do not trade, place orders, call brokers, write ledgers, or approve live trading.

```bash
aurora reports packet --run-dir data/research_runs/<run_id>
aurora reports packet --run-dir data/research_runs/<run_id> --create-zip
```

## Project Status Snapshots

AURORA can write a local project status snapshot to `data/status/project_status.json` and `data/status/project_status.md`. The snapshot summarizes current capabilities, safety boundaries, artifact locations, recent research runs, and paper simulation review status when available.

Project status snapshots are documentation-only. They do not trade, place orders, call brokers, write ledgers, or approve live trading.

```bash
aurora reports status --latest-test-count 293
```

## Safety Boundary Audits

AURORA can run a deterministic static safety audit over local source files. The audit scans for prohibited or risky patterns, then writes `data/status/safety_audit.json` and `data/status/safety_audit.md`.

Safety boundary audits are static analysis only. They do not trade, place orders, call brokers, call external APIs, write ledgers, or approve live trading.

```bash
aurora reports safety-audit
```

## Local Demo Workflow

AURORA includes a one-command local demo that uses deterministic synthetic OHLCV data. It registers a safe demo strategy, runs the research artifact workflow in `cache_only` mode, and writes review, readiness, plan, packet, status snapshot, and optional safety audit artifacts under `data/demo`.

The demo does not call yfinance, brokers, external APIs, or external LLMs. It does not trade, place orders, write ledgers, or approve live trading. Demo metrics are illustrative workflow outputs only and are not profitability claims.

If you later run local paper simulation from the generated plan, you can run `aurora execution review-paper-sim` afterward; artifact packets and project status snapshots will surface `paper_simulation/paper_sim_review.json` when it exists.

```bash
aurora demo run --latest-test-count 293
```

## Dashboard

AURORA includes a local Streamlit dashboard for inspecting cache files, model artifacts, strategy registry entries, backtest outputs, risk decisions, ledger state, and generated reports. It reads local files only, does not connect to Alpaca, and does not place orders.

The dashboard also includes Guided Workflow and Demo Workflow tabs. Guided Workflow walks through Strategy Prompt Lab, research runs, review, readiness, paper simulation planning, artifact packets, status snapshots, and safety audits. Demo Workflow runs the deterministic synthetic local demo. Both tabs are local research and artifact orchestration only. They do not trade, place orders, call brokers, or approve live trading.

```bash
streamlit run src/aurora/dashboard/streamlit_app.py
```

## Roadmap

1. Project scaffold, safe defaults, and importable modules.
2. Configuration validation and strategy schema hardening.
3. `yfinance` data adapter with normalization and quality checks.
4. Strategy registry and feature generation primitives.
5. Backtesting and walk-forward validation.
6. Risk manager integration and reporting.
7. Streamlit research dashboard.
8. Strategy Prompt Lab for structured strategy candidate generation.
9. Alpaca paper trading adapter.
10. LSEG Workspace adapter.

## Safety Principles

- Default mode is `research`.
- Live trading is not implemented.
- Broker adapter stubs are disabled by default.
- Approval gates are required in execution configuration.
- Risk limits are part of the default configuration.
