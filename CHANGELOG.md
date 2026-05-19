# Changelog

All notable changes to AURORA Trading Research will be documented in this file.

## Unreleased

## v2.1.0-rc1 - 2026-05-19

### Added

- **Phase 2B - LSEG Client Boundary**: Optional dependency `lseg` for market data. RealLSEGClient fails closed when SDK not installed or credentials missing. Secrets never exposed in repr/str/health_check messages.
- **Phase 3A - Alpaca Paper-Only Adapter**: AlpacaPaperBrokerProtocol with paper-only methods. RealAlpacaPaperClient blocks live trading, requires paper account. FakeAlpacaPaperClient for tests/dry-run. Default disabled, opt-in via environment.
- **Phase 3B - Paper Execution Path**: PaperExecutor gates all orders through RiskManager. PaperExecutionRequest/Result dataclasses. Ledger records all decisions (APPROVED/REJECTED/KILL_SWITCH) to JSONL. Never calls broker without RiskManager approval.
- **Phase 4A - Adaptive Strategy Optimizer**: AdaptiveOptimizer reads research artifacts (manifest, backtest, diagnostics, review). Deterministic proposals: REJECTED, NEEDS_MORE_RESEARCH, PROPOSED_FOR_REVIEW. Simple rules (Sharpe < 0.5, drawdown > 0.3, win_rate < 0.4 trigger NEEDS_MORE_RESEARCH). Never claims profitability. CLI: `aurora optimize analyze`.

### Safety

- All new modules follow existing safety boundaries.
- No live trading, no real broker execution, no real API calls.
- Alpaca live trading explicitly blocked - raises AlpacaLiveTradingError.
- All execution paths go through RiskManager gate.
- Optimizer is research-only, never calls brokers or executes trades.

### Added (from previous)

- Optional local ZIP export for Research Artifact Packets. ZIP export packages the packet manifest and copied local packet artifacts only; it does not trade, place orders, call brokers, write ledgers, or approve live trading.
- Guided Workflow dashboard tab for walking through the local research artifact pipeline from Prompt Lab through safety audit. The workflow reuses existing local research and artifact functions and does not trade, place orders, call brokers, or approve live trading.
- Deterministic local demo workflow that generates synthetic OHLCV data and runs the artifact pipeline without network, broker, execution, or ledger writes.
- Local paper simulation from approved paper simulation plans. The workflow uses the existing local SimulationBroker, PaperLedger, and RiskManager hard gate, writes under the run directory by default, and does not place real orders, call brokers, or approve live trading.
- Local paper simulation review/audit artifact that summarizes existing local simulation orders, risk decisions, account state, and positions without executing simulation or writing ledger files.
- Paper simulation review artifacts are now surfaced by project status snapshots and included in artifact packets when present.
- Future paper broker integration safety design document for controlled, paper-only adapter work in a later milestone.
- Disabled paper broker adapter interface and Alpaca paper adapter stub scaffolding for future controlled integration work.
- v2 release-candidate documentation and safety status updates.

## v1.0.0-rc1 - 2026-05-18

Release candidate for the first GitHub-ready AURORA v1 package.

### Added

- Market data layer with normalized OHLCV schema, yfinance adapter, quality checks, and local CSV cache.
- Feature engineering layer for returns, moving averages, volatility, RSI, MACD, ATR, drawdown, rolling highs/lows, and volume change.
- Baseline model training and local model registry.
- Strategy registry and long/flat signal generation.
- Research-only backtesting engine.
- Validation and overfitting diagnostics.
- Risk manager hard gate.
- Local simulation broker and paper ledger for local-only simulation workflows.
- Reporting utilities and Streamlit dashboard MVP.
- Deterministic Strategy Prompt Lab for validated strategy config drafts.
- Local research run orchestration with manifest safety flags.
- Strategy Candidate Review Board.
- Paper Simulation Readiness Gate.
- Paper Simulation Plan.
- Research Artifact Packet Builder.
- Project Status Snapshot.
- Safety Boundary Audit.
- End-to-end local artifact workflow fixture test.

### Safety

- No live trading in v1.
- No real broker execution.
- No real order placement.
- No direct order placement from prompts.
- No external LLM/API calls.
- No real API keys in the repository.
- No profitability claims.
