"""yfinance market data source adapter."""

import pandas as pd
import yfinance as yf

from aurora.data.base import DataSourceHealth, MarketDataRequest, MarketDataSource, utc_now_iso
from aurora.data.exceptions import DataSourceError, DataNormalizationError
from aurora.data.normalize import normalize_ohlcv


class YFinanceDataSource(MarketDataSource):
    """Market data adapter backed by yfinance."""

    source_name = "yfinance"

    def __init__(self) -> None:
        self.client = yf

    def health_check(self) -> DataSourceHealth:
        """Return a lightweight yfinance adapter health status."""
        return DataSourceHealth(
            source_name=self.source_name,
            ok=True,
            message="yfinance adapter is importable.",
            checked_at=utc_now_iso(),
        )

    def get_bars(self, request: MarketDataRequest) -> pd.DataFrame:
        """Download and normalize OHLCV bars from yfinance."""
        symbols = _clean_symbols(request.symbols)
        if not symbols:
            raise DataSourceError("At least one symbol is required.")

        try:
            raw = self.client.download(
                tickers=" ".join(symbols),
                start=request.start,
                end=request.end,
                interval=request.interval,
                auto_adjust=False,
                progress=False,
                group_by="column",
            )
        except Exception as exc:  # pragma: no cover - exact yfinance exceptions vary
            raise DataSourceError(f"yfinance download failed: {exc}") from exc

        if raw is None or raw.empty:
            raise DataSourceError("yfinance returned no data for the request.")

        try:
            if len(symbols) == 1:
                single = _extract_single_symbol_frame(raw, symbols[0])
                return normalize_ohlcv(single, source=self.source_name, symbol=symbols[0])

            frames = []
            for symbol in symbols:
                symbol_frame = _extract_multi_symbol_frame(raw, symbol)
                if not symbol_frame.empty:
                    frames.append(normalize_ohlcv(symbol_frame, source=self.source_name, symbol=symbol))
        except DataNormalizationError as exc:
            raise DataSourceError(f"Could not normalize yfinance data: {exc}") from exc

        if not frames:
            raise DataSourceError("yfinance returned no usable symbol data for the request.")
        return pd.concat(frames, ignore_index=True)


def _clean_symbols(symbols: list[str]) -> list[str]:
    return [symbol.strip().upper() for symbol in symbols if symbol.strip()]


def _extract_single_symbol_frame(raw: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if isinstance(raw.columns, pd.MultiIndex):
        return _extract_multi_symbol_frame(raw, symbol)
    return raw


def _extract_multi_symbol_frame(raw: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if not isinstance(raw.columns, pd.MultiIndex):
        return raw

    levels = raw.columns.nlevels
    for level in range(levels):
        level_values = [str(value).upper() for value in raw.columns.get_level_values(level)]
        if symbol.upper() in level_values:
            selected = raw.xs(symbol, axis=1, level=level, drop_level=True)
            return selected.dropna(how="all")

    return pd.DataFrame()
