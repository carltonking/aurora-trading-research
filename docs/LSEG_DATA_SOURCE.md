# LSEG Data Source Adapter

## Current Status

**Phase 2A**: Configuration and documentation scaffold. The LSEG adapter is currently a scaffold that requires an injected client to function. No LSEG SDK dependency has been added yet.

## Adapter Overview

The `LSEGDataSource` conforms to the `MarketDataSource` interface and provides:
- OHLCV data normalization into the standard schema
- Configurable asset type and currency
- Fail-closed behavior when credentials or client are missing

## Required Configuration

Configuration is loaded **exclusively from environment variables**. No configuration files or hardcoded credentials.

| Environment Variable | Required | Description |
|---------------------|----------|-------------|
| `LSEG_ENABLED` | No | Set to `true` or `1` to enable the adapter. Defaults to `false`. |
| `LSEG_APP_KEY` | Yes* | LSEG API application key. |
| `LSEG_USERNAME` | Yes* | LSEG username. |
| `LSEG_PASSWORD` | Yes* | LSEG password. |

*Required only when `LSEG_ENABLED=true`.

## Placeholder Configuration

Copy `.env.example` to `.env` and uncomment the LSEG variables:

```bash
# In .env (do not commit real credentials)
LSEG_ENABLED=false
LSEG_APP_KEY=<your-lseg-app-key>
LSEG_USERNAME=<your-lseg-username>
LSEG_PASSWORD=<your-lseg-password>
```

## No Real Network Calls in Tests

Tests do not make external network calls. The adapter requires an injected client that conforms to the `LSEGOHLCVClient` protocol:

```python
class LSEGOHLCVClient(Protocol):
    def get_ohlcv(
        self,
        *,
        symbols: list[str],
        start: str,
        end: str | None,
        interval: str,
        adjusted: bool,
    ) -> Any:
        """Return raw OHLCV data for requested symbols."""
```

Mock clients are used in tests to verify:
- Health check behavior
- Data normalization
- Error handling for missing config
- Response parsing

## Fail-Closed Behavior

The adapter fails closed when:
1. `LSEG_ENABLED` is not set to `true`/`1`
2. Any of `LSEG_APP_KEY`, `LSEG_USERNAME`, `LSEG_PASSWORD` is missing
3. No client has been injected

The `health_check()` method returns:
- `ok=False` with a message listing missing fields (field names only, no values)
- The message includes "enabled", "app_key", "username", "password", "client" as appropriate

The `get_bars()` method raises `DataSourceError` if the adapter is not ready.

## Client Injection

A real LSEG client will be injected via the `client` parameter:

```python
from aurora.data.lseg_source import LSEGDataSource, load_lseg_config_from_env

config = load_lseg_config_from_env()
source = LSEGDataSource(config=config, client=real_lseg_client)
```

The client injection pattern allows:
- Dependency injection for testing
- Lazy initialization of the LSEG SDK
- Swappable client implementations

## yfinance Remains Default

yfinance is the first implemented live market data source and remains the default for local development. The LSEG adapter is opt-in via environment configuration.