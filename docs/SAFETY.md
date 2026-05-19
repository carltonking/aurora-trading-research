# AURORA Safety Posture

AURORA Trading Research is research-first and paper-trading-first. Version 1 established local research, auditability, and safety review. The current v2 release-candidate work adds local paper simulation from approved plans, local simulation review artifacts, and disabled broker adapter stubs.

No live trading approval exists.

## Boundaries

- No live trading.
- No real broker execution.
- No real order placement.
- No direct order placement from prompts.
- No external LLM/API calls.
- No real API keys or secrets should be committed.
- No profitability claims.

## Safety Layers

- Strategy configs are validated before registration.
- Strategy Prompt Lab creates structured configs only; it does not generate executable strategy code or orders.
- Strategies generate long/flat signals, not orders.
- Backtesting and validation are research-only.
- RiskManager is a hard gate for future execution paths.
- Research runs write manifests with safety flags.
- Local simulation remains local-only and does not connect to live brokers.
- Local paper simulation from plan requires prior review/readiness/plan artifacts and still uses only the local simulation path.
- Paper simulation review consumes existing local simulation artifacts; it does not execute simulation.
- Readiness and plan artifacts do not execute simulation.
- Disabled broker adapter stubs are non-networked, dry-run-only scaffolding.
- The staged artifact pipeline is: research run -> review board -> readiness gate -> paper sim plan -> optional local paper simulation -> paper sim review -> artifact packet -> status snapshot -> safety audit.
- Review, readiness, paper simulation plan, paper simulation review, artifact packet, project status, and safety audit layers consume local artifacts and write local audit outputs only.

## Credentials

The repository should contain only placeholder environment examples. Future paper-only broker credentials, if any, must remain local and uncommitted.

## Future Paper Broker Integrations

Future paper broker integrations must follow [PAPER_BROKER_INTEGRATION.md](PAPER_BROKER_INTEGRATION.md). That document is design-only. The current broker package contains disabled interface/stub scaffolding only: it does not implement an actual broker client, require API keys, call networks, or approve live trading.

Live trading remains out of scope. Any future paper broker adapter must remain paper-only by default, require completed research/review/readiness/plan artifacts, require `RiskManager` approval for every candidate, and fail closed on unsafe or ambiguous state.

## Release Verification

Use [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) before publishing a release candidate or tagged release.
