# Alpaca Paper Broker Adapter

## Overview

The Alpaca adapter provides a paper-trading interface to Alpaca's API. **Live trading is explicitly unsupported** and will be blocked.

## Current Status

**Phase 3A**: Paper-only broker adapter design. This adapter is disabled by default and requires explicit configuration.

## Key Features

- **Paper-only**: Live trading is blocked. The adapter validates that the account is a paper account.
- **Default disabled**: Must set `ALPACA_PAPER_ENABLED=true` to enable.
- **Fail-closed**: If credentials are missing or SDK not installed, the adapter raises clear errors.
- **Secrets masked**: All representations use `***` for API keys and secrets.

## Configuration

Configuration is loaded **exclusively from environment variables**:

| Environment Variable | Required | Description |
|---------------------|----------|-------------|
| `ALPACA_PAPER_ENABLED` | No | Set to `true` or `1` to enable (default: false) |
| `ALPACA_PAPER_API_KEY` | Yes* | Alpaca paper API key |
| `ALPACA_PAPER_SECRET_KEY` | Yes* | Alpaca paper secret key |

*Required only when `ALPACA_PAPER_ENABLED=true`.

## Installation

To use the real Alpaca client:

```bash
pip install .[alpaca]
```

This installs the `alpaca-py` package. Without it, a `FakeAlpacaPaperClient` is used.

## Placeholder Configuration

Copy `.env.example` to `.env` and uncomment the Alpaca variables:

```bash
# In .env (do not commit real credentials)
ALPACA_PAPER_ENABLED=false
ALPACA_PAPER_API_KEY=<your-paper-api-key>
ALPACA_PAPER_SECRET_KEY=<your-paper-secret-key>
```

## Protocol

The adapter implements `AlpacaPaperBrokerProtocol`:

```python
@runtime_checkable
class AlpacaPaperBrokerProtocol(Protocol):
    def health_check(self) -> dict[str, Any]: ...
    def get_account(self) -> dict[str, Any]: ...
    def submit_paper_order(self, symbol, qty, side, order_type) -> dict[str, Any]: ...
    def cancel_paper_order(self, order_id) -> dict[str, Any]: ...
    def get_paper_positions(self) -> list[dict[str, Any]]: ...
    def get_paper_orders(self) -> list[dict[str, Any]]: ...
```

## Fail-Closed Behavior

The adapter fails closed when:
1. `ALPACA_PAPER_ENABLED` is not set to `true`/`1` → raises `ValueError`
2. `ALPACA_PAPER_API_KEY` or `ALPACA_PAPER_SECRET_KEY` is missing → raises `ValueError`
3. SDK not installed → raises `ImportError`
4. Live account detected → raises `AlpacaLiveTradingError`

## Secrets Protection

All representations mask secrets:
- `AlpacaConfig`: `api_key=***, secret_key=***`
- `RealAlpacaPaperClient`: Same masking

## No Real Network Calls in Tests

Tests use `FakeAlpacaPaperClient` which:
- Never makes network calls
- Returns canned responses
- Always reports as paper trading

## Live Trading Blocked

The adapter checks that the account is a paper account. If a live account is detected:

```python
raise AlpacaLiveTradingError(
    "Live trading is not supported. Only paper trading is allowed."
)
```

This ensures the adapter cannot be used for real-money trading.