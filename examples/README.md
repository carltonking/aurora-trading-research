# AURORA Examples

The files in this directory are safe local examples for research workflows.

- Strategy examples are configuration drafts for signal generation only.
- They do not place orders, call brokers, or enable live trading.
- They do not contain real API keys or credentials.
- They should be registered, used to generate signals, backtested, validated, reviewed, and gated before any future local paper simulation workflow.

Suggested local workflow:

```bash
aurora strategies validate --config-path examples/strategies/momentum_example.yaml
aurora strategies register --config-path examples/strategies/momentum_example.yaml
aurora strategies list
```

Generated artifacts should stay under local ignored directories such as `data/cache`, `data/research_runs`, `data/status`, and `data/reports`.
