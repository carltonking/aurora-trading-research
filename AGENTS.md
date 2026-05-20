# AURORA Trading Research - Agent Instructions

## Product Boundary

AURORA is a research-first, paper-trading-first algorithmic trading research platform.

Do not implement live trading.
Do not implement real-money trading.
Do not implement direct order placement from prompts.
Do not add live broker execution.
Do not commit API keys, secrets, tokens, credentials, or account identifiers.
Do not make profitability claims.
Do not bypass RiskManager.
Do not allow any execution path where a strategy signal directly places an order.
Do not allow Alpaca live trading - must block and raise AlpacaLiveTradingError.
Do not allow optimizer to call brokers or execute trades.

All strategy outputs must remain signals or reviewed candidates before execution.
Every paper execution candidate must pass RiskManager before any simulated or paper-broker action.
All paper execution must go through PaperExecutor which gates through RiskManager.
Optimizer must only read research artifacts and produce proposals - never trade or call brokers.

## Current Architecture

Package root: src/aurora

Important modules:
- src/aurora/data: market data sources, normalization, quality checks
- src/aurora/features: feature engineering
- src/aurora/models: training, labels, prediction, registry
- src/aurora/strategies: strategy configs and signal generation
- src/aurora/backtesting: research-only backtesting
- src/aurora/risk: RiskManager hard gate
- src/aurora/execution: local simulation, ledger, paper-simulation workflow, paper executor
- src/aurora/brokers: broker adapter interfaces (Alpaca paper-only, disabled stubs)
- src/aurora/reporting: reports, status, safety audit
- src/aurora/optimization: adaptive strategy optimizer (research-only)
- src/aurora/cli/app.py: Typer CLI entrypoint

## Testing Commands

Run before completion:

python3 -m pytest

PYTHONPATH=src python3 -m aurora.cli.app demo run --output-root data/demo --latest-test-count 824

PYTHONPATH=src python3 -m aurora.cli.app reports safety-audit --no-fail-on-critical

Expected current test count: 824 passed.

## Key Documentation

- `README.md` — Main project documentation with methodology overview and feature guide
- `docs/RESEARCH_PHILOSOPHY.md` — Detailed technical rationale for CPCV, DSR, leakage detection, and the multiple comparisons problem in strategy research
Expected safety audit status: WARN (45 findings), unless intentionally improved with matching tests and docs.

## Interface Parity (Phase 7C)

AURORA provides feature parity across three interfaces:

| Feature | CLI | Web UI | TUI |
|---------|-----|--------|-----|
| Data Explorer | aurora data | Yes | Yes |
| Strategy Builder | aurora strategy | Yes | Yes |
| Backtest Runner | aurora backtest | Yes | Yes |
| Paper Trading Monitor | aurora paper | Yes | Yes |
| Readiness Report | aurora report | Yes | Yes |
| Optimizer | aurora optimize | Yes | Yes |
| Export | aurora export | Yes | Yes |
| Scheduler | aurora scheduler | Yes | Yes (F9) |
| Deployment Checklist | aurora deploy | Yes | Yes |
| Settings | - | - | Yes (F10) |
| Logs | aurora logs | - | Yes (F11) |

All interfaces include mandatory disclaimers and do not support live trading.

## Implementation Rules

Prefer small, reviewable PRs.

For LSEG:
- Add a data adapter that conforms to MarketDataSource.
- Do not require real credentials for tests.
- Use dependency injection or a mock client for tests.
- Do not make external network calls in tests.
- Normalize into the standard OHLCV schema.
- Add explicit config/env handling.
- Fail closed when credentials or required config are missing.
- Add tests for health checks, missing config, mocked successful response, empty data, and normalization errors.

For Alpaca:
- Paper-only integration only.
- Keep live trading explicitly unsupported.
- Use environment variables for credentials.
- Do not commit credentials.
- Default to disabled/dry-run.
- Require explicit paper mode.
- Every order candidate must pass RiskManager before submission.
- Add tests proving rejected candidates are not submitted.
- Add tests proving live mode is blocked.

For adaptive strategy optimization:
- Build review-gated research optimization only.
- It may propose parameter changes and rerun research workflows.
- It must not directly trade.
- It must write artifacts explaining proposed changes, validation results, and review status.
- It must not claim guaranteed profitability.

For sandbox (strategy security):
- Sandbox must be enabled via AURORA_SANDBOX=true environment variable.
- External/community strategies must be validated via AST scanning before execution.
- Reject code with disallowed imports (os, sys, subprocess, socket, requests, threading, etc.).
- Reject dangerous builtins (exec, eval, compile, open for write).

For plugins:
- All plugins must pass secret detection (reject hardcoded API keys, tokens).
- Plugin registry must validate plugins implement required ABCs.
- Plugins are loaded only on-demand, never auto-executed.
- Paper-only broker plugins must enforce paper trading.

For deployment checklist:
- Checklist is advisory only - never grants permission to trade live.
- Always include mandatory disclaimer in reports.
- User bears full responsibility for trading decisions.

## Git Hygiene

Do not commit:
- __pycache__/
- .venv/
- data/demo/
- data/status/
- real model artifacts
- secrets
- API keys
