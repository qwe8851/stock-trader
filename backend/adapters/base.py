"""
Abstract base class for exchange adapters.

All exchange integrations (Binance, Upbit, etc.) implement this interface,
ensuring the trading engine remains exchange-agnostic.
"""
from abc import ABC, abstractmethod
from collections.abc import Callable, Awaitable
from typing import Any


class BaseExchangeAdapter(ABC):
    """
    Abstract interface that every exchange adapter must implement.

    Design principles:
    - All methods are async to support concurrent operations.
    - Return types use plain Python dicts/lists so the upper layers
      are not coupled to any SDK-specific models.
    - stream_tickers drives a WebSocket subscription and publishes
      data via a callback; the implementation decides the transport
      (e.g. Redis pub/sub).
    """

    # -------------------------------------------------------------------------
    # Market data
    # -------------------------------------------------------------------------

    @abstractmethod
    async def get_ohlcv(
        self,
        symbol: str,
        interval: str,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """
        Fetch historical OHLCV (candlestick) data.

        Args:
            symbol:   Trading pair, e.g. "BTCUSDT".
            interval: Candle interval string, e.g. "1m", "5m", "1h", "1d".
            limit:    Maximum number of candles to return (newest last).

        Returns:
            List of dicts with keys:
              time (int, Unix ms), open, high, low, close, volume,
              quote_volume, num_trades.
        """
        ...

    @abstractmethod
    async def stream_tickers(
        self,
        symbol: str,
        callback: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        """
        Subscribe to a real-time kline/ticker WebSocket stream.

        This method runs indefinitely (until cancelled) and calls
        ``callback`` with each incoming message.  Implementations are
        expected to reconnect automatically on transient failures.

        Args:
            symbol:   Trading pair, e.g. "BTCUSDT".
            callback: Async callable invoked for every tick.
        """
        ...

    # -------------------------------------------------------------------------
    # Order management (requires API credentials)
    # -------------------------------------------------------------------------

    @abstractmethod
    async def place_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float | None = None,
    ) -> dict[str, Any]:
        """
        Place a new order.

        Args:
            symbol:   Trading pair.
            side:     "BUY" or "SELL".
            quantity: Amount of base asset to trade.
            price:    Limit price; if None, a market order is placed.

        Returns:
            Exchange order response dict.
        """
        ...

    @abstractmethod
    async def cancel_order(
        self,
        symbol: str,
        order_id: str,
    ) -> dict[str, Any]:
        """
        Cancel an open order.

        Args:
            symbol:   Trading pair.
            order_id: Exchange-assigned order identifier.

        Returns:
            Exchange cancel response dict.
        """
        ...

    @abstractmethod
    async def get_balance(self) -> dict[str, Any]:
        """
        Retrieve account balances for all assets.

        Returns:
            Dict mapping asset symbol to {"free": str, "locked": str}.
        """
        ...

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    async def close(self) -> None:
        """
        Release any resources held by the adapter (e.g. HTTP sessions).
        Override in subclasses that maintain persistent connections.
        """
        pass
