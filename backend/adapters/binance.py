"""
Binance exchange adapter.

Implements BaseExchangeAdapter using the python-binance AsyncClient.
Price streaming publishes normalised candle data to the Redis pub/sub
channel "prices:{symbol}" so any number of WebSocket clients can
subscribe without creating additional Binance connections.
"""
import asyncio
import json
from collections.abc import Callable, Awaitable
from typing import Any

from binance import AsyncClient, BinanceSocketManager
from binance.exceptions import BinanceAPIException

from adapters.base import BaseExchangeAdapter
from core.config import settings
from core.logging import get_logger
from db.redis import get_redis

logger = get_logger(__name__)

# Redis channel template
PRICE_CHANNEL = "prices:{symbol}"

# Reconnect back-off (seconds)
_RECONNECT_INITIAL_DELAY = 1.0
_RECONNECT_MAX_DELAY = 60.0


class BinanceAdapter(BaseExchangeAdapter):
    """
    Binance implementation of BaseExchangeAdapter.

    When API credentials are absent the adapter operates in read-only
    mode - market data endpoints are available, order endpoints raise
    a RuntimeError.
    """

    def __init__(self) -> None:
        self._client: AsyncClient | None = None
        self._bsm: BinanceSocketManager | None = None

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    async def _get_client(self) -> AsyncClient:
        """Lazily create (or return the existing) AsyncClient."""
        if self._client is None:
            if settings.has_binance_credentials:
                self._client = await AsyncClient.create(
                    api_key=settings.BINANCE_API_KEY,
                    api_secret=settings.BINANCE_SECRET_KEY,
                    testnet=settings.BINANCE_TESTNET,
                )
                logger.info("Binance AsyncClient created with API credentials")
            else:
                # Public endpoints work without credentials
                self._client = await AsyncClient.create()
                logger.info(
                    "Binance AsyncClient created in public (no-auth) mode"
                )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.close_connection()
            self._client = None
            logger.info("Binance AsyncClient closed")

    # -------------------------------------------------------------------------
    # Market data
    # -------------------------------------------------------------------------

    async def get_ohlcv(
        self,
        symbol: str,
        interval: str = "1m",
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """
        Fetch historical klines from Binance REST API.

        Returns a list of normalised candle dicts (newest last).
        """
        client = await self._get_client()
        try:
            raw = await client.get_klines(
                symbol=symbol.upper(),
                interval=interval,
                limit=limit,
            )
        except BinanceAPIException as exc:
            logger.error(
                "Binance API error fetching OHLCV",
                extra={"symbol": symbol, "code": exc.code, "msg": exc.message},
            )
            raise

        return [_normalise_kline(k) for k in raw]

    # -------------------------------------------------------------------------
    # Real-time streaming
    # -------------------------------------------------------------------------

    async def stream_tickers(
        self,
        symbol: str,
        callback: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        """
        Subscribe to the Binance kline WebSocket and invoke ``callback``
        for every completed (or in-progress) candle update.

        Also publishes the normalised candle to Redis pub/sub so that
        browser clients can subscribe via the /ws/prices/{symbol} endpoint
        without each needing their own Binance connection.

        Automatically reconnects with exponential back-off on failure.
        """
        delay = _RECONNECT_INITIAL_DELAY
        sym = symbol.upper()

        while True:
            try:
                client = await self._get_client()
                bsm = BinanceSocketManager(client)

                async with bsm.kline_socket(symbol=sym, interval="1m") as stream:
                    logger.info(
                        "Binance kline WebSocket connected",
                        extra={"symbol": sym},
                    )
                    delay = _RECONNECT_INITIAL_DELAY  # reset on successful connect

                    while True:
                        msg = await stream.recv()
                        if msg is None:
                            break
                        if msg.get("e") == "error":
                            logger.warning(
                                "Binance stream error event",
                                extra={"msg": msg},
                            )
                            break

                        candle = _normalise_ws_kline(msg)

                        # Publish to Redis so all browser WS clients receive it
                        try:
                            redis = get_redis()
                            channel = PRICE_CHANNEL.format(symbol=sym)
                            await redis.publish(channel, json.dumps(candle))
                        except Exception as redis_exc:
                            logger.warning(
                                "Redis publish failed",
                                extra={"error": str(redis_exc)},
                            )

                        # Invoke the supplied callback
                        await callback(candle)

            except asyncio.CancelledError:
                logger.info("Binance stream_tickers cancelled", extra={"symbol": sym})
                raise
            except Exception as exc:
                logger.error(
                    "Binance WebSocket error - reconnecting",
                    extra={"symbol": sym, "error": str(exc), "delay": delay},
                )
                # Reset client so a fresh one is created on reconnect
                await self.close()
                await asyncio.sleep(delay)
                delay = min(delay * 2, _RECONNECT_MAX_DELAY)

    # -------------------------------------------------------------------------
    # Order management
    # -------------------------------------------------------------------------

    def _require_credentials(self) -> None:
        if not settings.has_binance_credentials:
            raise RuntimeError(
                "Binance API credentials are required for order operations. "
                "Set BINANCE_API_KEY and BINANCE_SECRET_KEY in your environment."
            )

    async def place_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float | None = None,
    ) -> dict[str, Any]:
        self._require_credentials()

        if settings.LIVE_TRADING_ENABLED is False and not settings.PAPER_TRADING_MODE:
            raise RuntimeError("Live trading is disabled. Enable LIVE_TRADING_ENABLED.")

        client = await self._get_client()
        try:
            if price is not None:
                order = await client.create_order(
                    symbol=symbol.upper(),
                    side=side.upper(),
                    type="LIMIT",
                    timeInForce="GTC",
                    quantity=quantity,
                    price=str(price),
                )
            else:
                order = await client.create_order(
                    symbol=symbol.upper(),
                    side=side.upper(),
                    type="MARKET",
                    quantity=quantity,
                )
            logger.info(
                "Order placed",
                extra={"symbol": symbol, "side": side, "order_id": order.get("orderId")},
            )
            return order
        except BinanceAPIException as exc:
            logger.error(
                "Binance order placement failed",
                extra={"symbol": symbol, "code": exc.code, "msg": exc.message},
            )
            raise

    async def cancel_order(
        self,
        symbol: str,
        order_id: str,
    ) -> dict[str, Any]:
        self._require_credentials()
        client = await self._get_client()
        try:
            result = await client.cancel_order(
                symbol=symbol.upper(),
                orderId=order_id,
            )
            logger.info(
                "Order cancelled",
                extra={"symbol": symbol, "order_id": order_id},
            )
            return result
        except BinanceAPIException as exc:
            logger.error(
                "Binance cancel order failed",
                extra={"symbol": symbol, "order_id": order_id, "code": exc.code},
            )
            raise

    async def get_balance(self) -> dict[str, Any]:
        self._require_credentials()
        client = await self._get_client()
        account = await client.get_account()
        balances = {
            b["asset"]: {"free": b["free"], "locked": b["locked"]}
            for b in account["balances"]
            if float(b["free"]) > 0 or float(b["locked"]) > 0
        }
        return balances


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalise_kline(k: list) -> dict[str, Any]:
    """Convert a raw REST kline list to a normalised dict."""
    return {
        "time": k[0],           # open time (Unix ms)
        "open": float(k[1]),
        "high": float(k[2]),
        "low": float(k[3]),
        "close": float(k[4]),
        "volume": float(k[5]),
        "close_time": k[6],
        "quote_volume": float(k[7]),
        "num_trades": k[8],
    }


def _normalise_ws_kline(msg: dict) -> dict[str, Any]:
    """Convert a raw WebSocket kline message to the same normalised format."""
    k = msg["k"]
    return {
        "time": k["t"],          # open time (Unix ms)
        "open": float(k["o"]),
        "high": float(k["h"]),
        "low": float(k["l"]),
        "close": float(k["c"]),
        "volume": float(k["v"]),
        "close_time": k["T"],
        "quote_volume": float(k["q"]),
        "num_trades": k["n"],
        "is_closed": k["x"],     # True when the candle is finalised
        "symbol": k["s"],
        "interval": k["i"],
        "event_time": msg["E"],
    }
