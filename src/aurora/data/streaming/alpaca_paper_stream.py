"""Alpaca paper trading WebSocket stream."""

import os
from typing import Optional

from aurora.data.streaming.base import Bar, MarketDataStream


class AlpacaLiveTradingError(Exception):
    """Raised when attempting to use live trading instead of paper."""
    pass


class AlpacaSDKNotInstalledError(Exception):
    """Raised when Alpaca SDK is not installed."""
    pass


class AlpacaPaperStream(MarketDataStream):
    """Alpaca paper trading WebSocket stream for live price updates."""

    def __init__(self, api_key: Optional[str] = None, secret_key: Optional[str] = None) -> None:
        """Initialize Alpaca paper stream.

        Args:
            api_key: Alpaca paper API key (defaults to env ALPACA_PAPER_API_KEY)
            secret_key: Alpaca paper secret key (defaults to env ALPACA_PAPER_SECRET_KEY)
        """
        super().__init__()
        self._api_key = api_key or os.environ.get("ALPACA_PAPER_API_KEY")
        self._secret_key = secret_key or os.environ.get("ALPACA_PAPER_SECRET_KEY")
        self._ws = None
        self._symbols: list[str] = []

    def _ensure_sdk_installed(self) -> None:
        """Ensure alpaca-py is installed."""
        try:
            import alpaca  # noqa: F401
        except ImportError:
            raise AlpacaSDKNotInstalledError(
                "Alpaca SDK not installed. Install with: pip install alpaca-py"
            )

    def _get_client(self):
        """Get the Alpaca SDK client."""
        self._ensure_sdk_installed()
        from alpaca.data import CryptoDataClient, StockDataClient
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.trading import TradingClient

        if not self._api_key or not self._secret_key:
            raise ValueError(
                "Alpaca credentials not provided. Set ALPACA_PAPER_API_KEY and "
                "ALPACA_PAPER_SECRET_KEY environment variables."
            )

        trading_client = TradingClient(self._api_key, self._secret_key, paper_only=True)

        account = trading_client.get_account()
        if getattr(account, "account_type", "paper") != "paper":
            raise AlpacaLiveTradingError(
                "Live trading detected. AURORA only supports paper trading. "
                "Use paper API credentials or check account type."
            )

        return StockHistoricalDataClient(self._api_key, self._secret_key)

    def connect(self) -> None:
        """Connect to Alpaca paper WebSocket."""
        self._ensure_sdk_installed()

        if not self._api_key or not self._secret_key:
            raise ValueError(
                "Alpaca credentials not provided. Set ALPACA_PAPER_API_KEY and "
                "ALPACA_PAPER_SECRET_KEY environment variables."
            )

        try:
            from alpaca.data import StockDataStream
            self._ws = StockDataStream(self._api_key, self._secret_key, paper=True)
        except Exception as e:
            raise RuntimeError(f"Failed to connect to Alpaca stream: {e}")

        self._connected = True

    def disconnect(self) -> None:
        """Disconnect from Alpaca WebSocket."""
        if self._ws is not None:
            try:
                self._ws.close()
            except Exception:
                pass
        self._connected = False

    def subscribe(self, symbols: list[str]) -> None:
        """Subscribe to real-time bar updates."""
        if not self._connected:
            raise RuntimeError("Must connect before subscribing")

        self._symbols = symbols

        if self._ws is not None:
            self._ws.subscribe_quotes(self._on_quote, *symbols)
            self._ws.subscribe_bars(self._on_bar, *symbols)

    def _on_bar(self, bar) -> None:
        """Handle incoming bar from WebSocket."""
        if self._bar_callback is not None:
            aurora_bar = Bar(
                symbol=bar.symbol,
                timestamp=str(bar.timestamp),
                open=float(bar.open),
                high=float(bar.high),
                low=float(bar.low),
                close=float(bar.close),
                volume=int(bar.volume),
            )
            self._bar_callback(aurora_bar)

    def _on_quote(self, quote) -> None:
        """Handle incoming quote from WebSocket."""
        if self._quote_callback is not None:
            from aurora.data.streaming.base import Quote
            aurora_quote = Quote(
                symbol=quote.symbol,
                timestamp=str(quote.timestamp),
                bid=float(quote.bid_price),
                ask=float(quote.ask_price),
                bid_size=int(quote.bid_size),
                ask_size=int(quote.ask_size),
            )
            self._quote_callback(aurora_quote)