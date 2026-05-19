"""LSEG client interface and optional real client implementation.

This module defines the protocol for LSEG clients and provides an optional
RealLSEGClient that requires the lseg-sdk package.

The real client is optional - it will only be available if the user installs
the [lseg] extra: pip install aurora-trading-research[lseg]
"""

from typing import Any, Protocol, runtime_checkable

import pandas as pd

from aurora.data.lseg_source import LSEGDataSourceConfig


@runtime_checkable
class LSEGClientProtocol(Protocol):
    """Protocol defining the interface for LSEG data clients.

    Any client used with LSEGDataSource must implement this protocol.
    """

    def health_check(self) -> dict[str, Any]:
        """Return health status of the LSEG connection.

        Returns:
            Dict with 'ok' (bool), 'message' (str), and optional 'details' (dict).
        """

    def get_ohlcv(
        self,
        *,
        symbols: list[str],
        start: str,
        end: str | None,
        interval: str,
        adjusted: bool,
    ) -> Any:
        """Fetch OHLCV data for the given symbols.

        Args:
            symbols: List of RIC codes to fetch (e.g., ['SPY.N', 'QQQ.N']).
            start: Start date in ISO format (YYYY-MM-DD).
            end: End date in ISO format (YYYY-MM-DD), or None for current date.
            interval: Data interval (e.g., '1d', '1h', '1m').
            adjusted: Whether to return adjusted prices.

        Returns:
            Raw OHLCV data in a format consumable by LSEGDataSource normalization.
        """


class LSEGConnectionError(Exception):
    """Raised when connection to LSEG API fails."""


class LSEGClient:
    """Real LSEG client that requires the lseg-sdk package.

    This client requires the optional lseg-sdk dependency. Install with:
        pip install aurora-trading-research[lseg]

    The client fails closed:
    - If credentials are missing in config, raises ValueError immediately.
    - If the SDK import fails, raises ImportError with clear message.
    - All network errors are caught and re-raised as LSEGConnectionError
      with secret-free messages.
    """

    _SDK_IMPORT_ERROR = (
        "LSEG SDK not installed. Install with: pip install .[lseg]"
    )

    def __init__(self, config: LSEGDataSourceConfig) -> None:
        if not config.app_key:
            raise ValueError("LSEG app_key is required.")
        if not config.username:
            raise ValueError("LSEG username is required.")
        if not config.password:
            raise ValueError("LSEG password is required.")

        self._config = config
        self._sdk = self._import_sdk()

    def _import_sdk(self) -> Any:
        try:
            import lseg
            return lseg
        except ImportError as exc:
            raise ImportError(self._SDK_IMPORT_ERROR) from exc

    def __repr__(self) -> str:
        return (
            f"LSEGClient("
            f"enabled={self._config.enabled}, "
            f"app_key={'***' if self._config.app_key else None}, "
            f"username={'***' if self._config.username else None}, "
            f"password={'***' if self._config.password else None})"
        )

    def __str__(self) -> str:
        return self.__repr__()

    def health_check(self) -> dict[str, Any]:
        try:
            session = self._sdk.Session(
                app_key=self._config.app_key,
                username=self._config.username,
                password=self._config.password,
            )
            session.open()
            session.close()
            return {
                "ok": True,
                "message": "LSEG connection successful.",
                "details": {"source": "lseg-sdk"},
            }
        except ImportError as exc:
            return {"ok": False, "message": str(exc), "details": {}}
        except Exception as exc:
            return {
                "ok": False,
                "message": f"LSEG connection failed: {type(exc).__name__}",
                "details": {},
            }

    def get_ohlcv(
        self,
        *,
        symbols: list[str],
        start: str,
        end: str | None,
        interval: str,
        adjusted: bool,
    ) -> Any:
        try:
            session = self._sdk.Session(
                app_key=self._config.app_key,
                username=self._config.username,
                password=self._config.password,
            )
            session.open()

            try:
                rics = ",".join(symbols)
                fields = "TRDPRC_1,TRDPRC_2,TRDPRC_3,TRDPRC_4,TRDPRC_5,TRDHG1,TRDLW1,VOLUME"

                if adjusted:
                    fields += ",ADJCLOSE"

                request = self._sdk.DataFramework.UsdSubscriptionRequest(
                    universe=[rics],
                    fields=[fields],
                    dateFrom=start,
                    dateTo=end or "",
                    interval=interval,
                )

                data = session.get_data(request)

                session.close()
                return data

            except Exception as exc:
                session.close()
                raise LSEGConnectionError(
                    f"LSEG data request failed: {type(exc).__name__}"
                ) from exc

        except ImportError as exc:
            raise LSEGConnectionError(str(exc)) from exc
        except Exception as exc:
            raise LSEGConnectionError(
                f"LSEG request failed: {type(exc).__name__}"
            ) from exc