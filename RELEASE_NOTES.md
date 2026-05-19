# AURORA Release Notes

## Summary

AURORA Trading Research is a research-first, paper-trading-first Python platform for local strategy research, validation, review, and audit packaging.

This release candidate packages the first complete local research workflow: market data normalization, feature generation, model experimentation, signal generation, research-only backtesting, diagnostics, review gates, readiness artifacts, reporting, and safety audits.

## v2 Release Candidate Update

The current v2 release-candidate feature set builds on `v1.0.0-rc1` with local workflow packaging and controlled paper-simulation preparation. It remains local-first and paper-trading-first.

### What Changed Since v1.0.0-rc1

- Optional artifact packet ZIP export.
- Guided Workflow dashboard tab.
- Deterministic local demo workflow with synthetic data.
- Local paper simulation from approved plans.
- Local paper simulation review/audit artifact.
- `paper_sim_review.json` visibility in packet and status workflows.
- Future paper broker integration safety design document.
- Disabled broker adapter interface and Alpaca paper stub scaffolding.

### Explicitly Out of Scope

- Live trading.
- Actual broker API integration.
- Real order placement.
- Real API keys or committed secrets.
- External LLM/API calls.
- Profitability guarantees or investment advice.

### v2 Local Verification

```bash
python3 -m pytest
PYTHONPATH=src python3 -m aurora.cli.app demo run --output-root data/demo --latest-test-count 293
PYTHONPATH=src python3 -m aurora.cli.app reports safety-audit --no-fail-on-critical
```

Latest verified v2 test result: `293 passed`.

The safety audit currently returns `WARN`. This is expected because the static scanner reports intentional local simulation/ledger modules, safety phrase constants, Prompt Lab unsupported-request constants, audit pattern definitions, and disabled broker adapter stub `submit_order` interfaces. These warnings are not live trading support and do not indicate a real broker integration.

## v1.0.0-rc1 Release Notes

## Who This Release Is For

- Researchers who want a modular local workflow for strategy candidate analysis.
- Developers reviewing a safe Python architecture for algorithmic trading research tooling.
- Users who need auditable local artifacts before considering future paper simulation workflows.

## What Is Included

- Market data, feature engineering, model training/registry, strategy registry, and signal generation.
- Research-only backtesting, validation, and overfitting diagnostics.
- Risk manager hard gate.
- Local-only simulation broker and paper ledger.
- Reporting utilities and local Streamlit dashboard.
- Deterministic Strategy Prompt Lab for structured config drafts.
- Research run orchestration with manifest safety flags.
- Review Board, Paper Simulation Readiness Gate, and Paper Simulation Plan.
- Research Artifact Packet Builder, Project Status Snapshot, and Safety Boundary Audit.
- End-to-end local artifact workflow fixture test.

## What Is Explicitly Not Included

- Live trading.
- Alpaca live trading.
- Real broker execution.
- Real order placement.
- Direct order placement from prompts.
- External LLM/API calls.
- Real API keys or secrets.
- Profitability guarantees or investment advice.

## Safety Posture

AURORA v1 is research-only and paper-trading-first. Strategies produce signals before any later execution path, and artifact gates document review status before future local paper simulation planning. No v1 artifact approves live trading.

## Local Verification

```bash
python3 -m pytest
PYTHONPATH=src python3 -m aurora.cli.app reports status --latest-test-count 293
PYTHONPATH=src python3 -m aurora.cli.app reports safety-audit --no-fail-on-critical
```

Latest verified test result: `293 passed`.

The safety audit currently returns `WARN`. This is expected because the static scanner reports intentional local simulation/ledger modules, safety phrase constants, Prompt Lab unsupported-request constants, and the audit pattern list itself. These warnings are not live trading support.

## Suggested Next Milestones

- v1.1: Improve dashboard usability, report browsing, and documentation examples.
- v1.1: Add more deterministic fixture datasets and strategy examples.
- v1.1: Continue local artifact packaging improvements, including optional ZIP exports.
- v2: Design paper-only adapter interfaces behind explicit safety and risk gates.
- v2: Evaluate external integrations only after a separate safety design review.

## Post-RC Development Note

Research Artifact Packets can optionally create a local `artifact_packet.zip` for sharing and review. ZIP export is local artifact packaging only. It does not trade, place orders, call brokers, write ledgers, or approve live trading.
