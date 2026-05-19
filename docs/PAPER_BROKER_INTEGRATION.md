# Future Paper Broker Integration Safety Design

This document defines safety requirements for a future paper broker integration. It is design-only.

No live trading is implemented. No broker adapter is implemented by this document. No API keys are required for current local workflows. Any future broker integration must be paper-only by default.

## Purpose

The purpose of this document is to define the architecture, safety gates, audit artifacts, and testing requirements that must exist before AURORA can add a future paper broker adapter, including a possible Alpaca paper adapter in a later milestone.

The current system remains local-first. Existing v2 workflows can generate research runs, reviews, readiness results, paper simulation plans, local paper simulation outputs, and artifact packets without broker credentials.

v2 now contains disabled broker adapter interface/stub scaffolding only. The Alpaca paper adapter stub is non-networked, dry-run-only, and does not implement broker submission.

## Current Stub Status

The current scaffolding is not an actual Alpaca integration. It does not include:

- An Alpaca client.
- Alpaca package dependencies.
- Network calls.
- Endpoint configuration.
- API key fields.
- Real or paper broker order placement.

The stub exists so future implementation work has a fail-closed interface and tests before any broker-paper behavior is considered.

## Non-Goals

- Live trading.
- Real-money order placement.
- Direct order placement from prompts.
- Bypassing `RiskManager`.
- Storing real API keys in the repository.
- External LLM/API-driven order generation.
- Profitability claims.

## Required Preconditions Before Any Future Broker Paper Order

A future broker paper order must require all of the following:

- A completed research run manifest.
- Review Board status `APPROVED_FOR_PAPER_SIMULATION`.
- Paper Simulation Readiness status `READY_FOR_PAPER_SIMULATION`.
- Paper Simulation Plan status `PLAN_READY`.
- Local paper simulation from plan completed.
- Paper Simulation Review status `PASS`, or `WARN` only when explicitly allowed by configuration.
- `RiskManager` hard gate approval for every candidate.
- An explicit user CLI command; never prompt-only execution.
- Paper-mode configuration confirmed.
- Live trading disabled by configuration and a code-level guard.

## Proposed Future Adapter Boundaries

A future implementation should define broker integration boundaries conceptually like this:

- `BrokerAdapter`: a narrow abstraction for broker-paper request handling.
- `PaperBrokerAdapter`: a paper-only implementation boundary.
- `AlpacaPaperBrokerAdapter`: a possible future paper-only adapter in a later version.

Required adapter behavior:

- Use paper endpoint only.
- Provide no live endpoint support.
- Provide no automatic trading loop.
- Provide no direct prompt-to-order path.
- Support explicit dry-run mode.
- Log requests and responses without secrets.
- Read configuration from environment variables only.
- Never store keys in the repository.
- Stay disabled unless explicitly enabled.

## Required Safety Flags

Any future broker-paper artifact must include:

- `paper_broker_only: true`
- `live_trading: false`
- `real_money: false`
- `risk_gate_required: true`
- `risk_gate_passed: true` or `risk_gate_passed: false`
- `external_llm_calls: false`
- `prompt_direct_order: false`

## Configuration Requirements

- `.env.example` must not include real keys.
- Real keys must never be committed.
- Broker credentials must be read only from environment variables or a local untracked secrets file.
- Paper mode must be explicit.
- Live mode must not be supported in v2.

## Audit and Logging Requirements

Future broker-paper runs must write:

- `broker_paper_manifest.json`
- Sanitized request log.
- Sanitized response log.
- Risk decision log.

The artifacts must contain:

- No secret values.
- No bearer tokens.
- No account secrets.
- No raw credentials.

## Testing Requirements

Future implementation must include tests proving:

- Live endpoint cannot be selected.
- Missing paper-mode configuration blocks execution.
- `RiskManager` is called for every candidate.
- Rejected risk decisions do not reach the adapter.
- Dry-run mode does not call the adapter.
- No secrets are written to artifacts or logs.
- Direct prompt order requests are blocked.
- No external LLM calls are made.

## Failure Handling

A future adapter must:

- Fail closed.
- Block on ambiguous environment.
- Block on missing readiness, plan, or review artifacts.
- Block on unsafe safety flags.
- Block on missing `RiskManager` approval.
- Never retry into live mode.
- Never downgrade a risk rejection.

## v2 Recommendation

v2 should remain local-first. Optional broker paper integration should be a later controlled milestone after local paper simulation review is stable.

Any future adapter work should start with this document, update the safety audit expectations, and add tests before enabling broker-paper behavior.
