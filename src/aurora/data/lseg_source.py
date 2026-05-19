"""LSEG market data source adapter scaffolding.

This adapter intentionally does not import an LSEG SDK or create network
clients. A caller must inject a client object that provides ``get_ohlcv``.

Configuration is loaded exclusively from environment variables:
- LSEG_ENABLED: Enable the adapter (default: false)
- LSEG_APP_KEY: LSEG API application key
- LSEG_USERNAME: LSEG username
- LSEG_PASSWORD: LSEG password
"""

import os
from dataclasses import dataclass
from typing import Any, Protocol

import pandas as pd

from aurora.data.base import DataSourceHealth, MarketDataRequest, MarketDataSource, utc_now_iso
from aurora.data.exceptions import DataSourceError, DataNormalizationError
from aurora.data.normalize import normalize_ohlcv


class LSEGOHLCVClient(Protocol):
    """Minimal protocol expected from an injected LSEG client."""

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


@dataclass(frozen=True)
class LSEGDataSourceConfig:
    """Configuration for the LSEG adapter scaffold."""

    enabled: bool = False
    app_key: str | None = None
    username: str | None = None
    password: str | None = None
    source_name: str = "lseg"
    asset_type: str = "equity"
    currency: str = "USD"

    def __repr__(self) -> str:
        return (
            f"LSEGDataSourceConfig("
            f"enabled={self.enabled}, "
            f"app_key={'***' if self.app_key else None}, "
            f"username={'***' if self.username else None}, "
            f"password={'***' if self.password else None}, "
            f"source_name={self.source_name!r}, "
            f"asset_type={self.asset_type!r}, "
            f"currency={self.currency!r})"
        )

    def __str__(self) -> str:
        return self.__repr__()


def load_lseg_config_from_env() -> LSEGDataSourceConfig:
    """Load LSEG configuration from environment variables only.

    Environment variables:
        LSEG_ENABLED: Set to 'true' or '1' to enable the adapter
        LSEG_APP_KEY: LSEG API application key
        LSEG_USERNAME: LSEG username
        LSEG_PASSWORD: LSEG password

    Returns:
        LSEGDataSourceConfig with values from environment or defaults.

    Note:
        This function does not validate credentials - it only loads them.
        The adapter will fail closed if credentials are incomplete.
    """
    enabled = os.getenv("LSEG_ENABLED", "").lower() in ("true", "1", "yes")
    app_key = os.getenv("LSEG_APP_KEY") or None
    username = os.getenv("LSEG_USERNAME") or None
    password = os.getenv("LSEG_PASSWORD") or None

    return LSEGDataSourceConfig(
        enabled=enabled,
        app_key=app_key,
        username=username,
        password=password,
    )


class LSEGDataSource(MarketDataSource):
    """Market data adapter scaffold for LSEG OHLCV data."""

    source_name = "lseg"

    def __init__(
        self,
        config: LSEGDataSourceConfig | None = None,
        client: LSEGOHLCVClient | None = None,
    ) -> None:
        self.config = config or LSEGDataSourceConfig()
        self.client = client
        self.source_name = self.config.source_name

    def health_check(self) -> DataSourceHealth:
        """Return health without making network calls."""
        missing = self._missing_config_reasons()
        if missing:
            return DataSourceHealth(
                source_name=self.source_name,
                ok=False,
                message="LSEG adapter disabled or missing config: " + ", ".join(missing),
                checked_at=utc_now_iso(),
            )
        return DataSourceHealth(
            source_name=self.source_name,
            ok=True,
            message="LSEG adapter config is present and an injected client is available.",
            checked_at=utc_now_iso(),
        )

    def get_bars(self, request: MarketDataRequest) -> pd.DataFrame:
        """Fetch and normalize OHLCV bars from an injected LSEG client."""
        self._raise_if_not_ready()
        symbols = _clean_symbols(request.symbols)
        if not symbols:
            raise DataSourceError("At least one symbol is required.")

        try:
            raw = self.client.get_ohlcv(
                symbols=symbols,
                start=request.start,
                end=request.end,
                interval=request.interval,
                adjusted=request.adjusted,
            )
        except Exception as exc:
            raise DataSourceError(f"LSEG client failed to return OHLCV data: {exc}") from exc

        frames = self._normalize_response(raw, symbols)
        if not frames:
            raise DataSourceError("LSEG returned no usable OHLCV data for the request.")
        return (
            pd.concat(frames, ignore_index=True)
            .sort_values(["symbol", "timestamp"])
            .reset_index(drop=True)
        )

    def _raise_if_not_ready(self) -> None:
        missing = self._missing_config_reasons()
        if missing:
            raise DataSourceError(
                "LSEG adapter is disabled or missing required config: " + ", ".join(missing)
            )

    def _missing_config_reasons(self) -> list[str]:
        missing: list[str] = []
        if not self.config.enabled:
            missing.append("enabled")
        if not self.config.app_key:
            missing.append("app_key")
        if not self.config.username:
            missing.append("username")
        if not self.config.password:
            missing.append("password")
        if self.client is None:
            missing.append("client")
        return missing

    def _normalize_response(self, raw: Any, symbols: list[str]) -> list[pd.DataFrame]:
        if raw is None:
            raise DataSourceError("LSEG returned no data for the request.")
        if isinstance(raw, dict):
            return self._normalize_dict_response(raw, symbols)
        raw_frame = _to_dataframe(raw)
        return self._normalize_frame_response(raw_frame, symbols)

    def _normalize_dict_response(
        self,
        raw: dict[Any, Any],
        symbols: list[str],
    ) -> list[pd.DataFrame]:
        if not raw:
            raise DataSourceError("LSEG returned no data for the request.")
        if any(symbol in raw for symbol in symbols):
            frames: list[pd.DataFrame] = []
            for symbol in symbols:
                if symbol not in raw:
                    continue
                symbol_frame = _to_dataframe(raw[symbol])
                if not symbol_frame.empty:
                    frames.append(self._normalize_symbol_frame(symbol_frame, symbol))
            return frames
        for key in ("data", "bars", "prices"):
            if key in raw:
                return self._normalize_frame_response(_to_dataframe(raw[key]), symbols)
        return self._normalize_frame_response(_to_dataframe(raw), symbols)

    def _normalize_frame_response(
        self,
        raw_frame: pd.DataFrame,
        symbols: list[str],
    ) -> list[pd.DataFrame]:
        if raw_frame.empty:
            raise DataSourceError("LSEG returned no data for the request.")
        if "symbol" in {str(column).strip().lower() for column in raw_frame.columns}:
            symbol_column = _find_column(raw_frame, "symbol")
            frames = []
            for symbol in symbols:
                symbol_frame = raw_frame[
                    raw_frame[symbol_column].astype(str).str.upper() == symbol
                ].copy()
                if not symbol_frame.empty:
                    frames.append(self._normalize_symbol_frame(symbol_frame, symbol))
            return frames
        if len(symbols) == 1:
            return [self._normalize_symbol_frame(raw_frame, symbols[0])]
        raise DataSourceError("LSEG multi-symbol response must include a symbol column.")

    def _normalize_symbol_frame(self, raw_frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
        try:
            normalized = normalize_ohlcv(
                raw_frame,
                source=self.source_name,
                symbol=symbol,
                asset_type=self.config.asset_type,
                currency=self.config.currency,
            )
        except DataNormalizationError as exc:
            raise DataSourceError(f"Could not normalize LSEG data: {exc}") from exc
        if normalized.empty:
            raise DataSourceError("LSEG returned no usable OHLCV rows after normalization.")
        return normalized


def _clean_symbols(symbols: list[str]) -> list[str]:
    return [symbol.strip().upper() for symbol in symbols if symbol.strip()]


def _to_dataframe(raw: Any) -> pd.DataFrame:
    if isinstance(raw, pd.DataFrame):
        return raw.copy()
    return pd.DataFrame(raw)


def _find_column(df: pd.DataFrame, name: str) -> Any:
    for column in df.columns:
        if str(column).strip().lower() == name:
            return column
    raise DataSourceError(f"LSEG response is missing required column: {name}.")
