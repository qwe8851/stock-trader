"""
WebSocket router - real-time price feed for browser clients.

Flow:
  Binance WS  →  BinanceAdapter  →  Redis pub/sub (channel: prices:{symbol})
                                         ↓
                              /ws/prices/{symbol}  →  Browser

Multiple browser clients can subscribe to the same symbol; each gets its own
WebSocket connection that independently reads from the Redis pub/sub channel.
"""
import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from redis.asyncio.client import PubSub

from adapters.binance import PRICE_CHANNEL
from db.redis import get_redis
from core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/prices/{symbol}")
async def prices_websocket(websocket: WebSocket, symbol: str) -> None:
    """
    Subscribe to real-time price updates for a trading pair.

    The endpoint subscribes to the Redis pub/sub channel that the
    BinanceAdapter writes to, then forwards every message to the
    connected browser client as JSON text.

    Args:
        symbol: Trading pair, e.g. "BTCUSDT" (case-insensitive).
    """
    sym = symbol.upper()
    channel = PRICE_CHANNEL.format(symbol=sym)

    await websocket.accept()
    logger.info(
        "WebSocket client connected",
        extra={"symbol": sym, "client": str(websocket.client)},
    )

    redis = get_redis()
    pubsub: PubSub = redis.pubsub()

    try:
        await pubsub.subscribe(channel)

        # Send an initial connection acknowledgement
        await websocket.send_json(
            {"type": "subscribed", "symbol": sym, "channel": channel}
        )

        while True:
            # Non-blocking read with a short timeout so we can detect
            # client disconnections promptly.
            message = await pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=1.0,
            )

            if message and message["type"] == "message":
                data = message["data"]
                # data is already a JSON string (published by BinanceAdapter)
                await websocket.send_text(data)

            # Yield control so other coroutines can run
            await asyncio.sleep(0)

    except WebSocketDisconnect:
        logger.info(
            "WebSocket client disconnected",
            extra={"symbol": sym},
        )
    except asyncio.CancelledError:
        logger.info("WebSocket handler cancelled", extra={"symbol": sym})
    except Exception as exc:
        logger.error(
            "WebSocket error",
            extra={"symbol": sym, "error": str(exc)},
        )
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass
    finally:
        try:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
        except Exception:
            pass
        logger.info("WebSocket pubsub cleaned up", extra={"symbol": sym})


@router.websocket("/ws/prices/{symbol}/history")
async def prices_history_websocket(
    websocket: WebSocket,
    symbol: str,
    interval: str = "1m",
    limit: int = 200,
) -> None:
    """
    On connection: send the last ``limit`` candles for the symbol, then close.
    Useful for seeding the chart before the live feed kicks in.
    """
    from adapters.binance import BinanceAdapter

    sym = symbol.upper()
    await websocket.accept()

    try:
        adapter = BinanceAdapter()
        candles = await adapter.get_ohlcv(sym, interval=interval, limit=limit)
        await websocket.send_json({"type": "history", "symbol": sym, "data": candles})
    except Exception as exc:
        logger.error(
            "History WebSocket error",
            extra={"symbol": sym, "error": str(exc)},
        )
        await websocket.send_json({"type": "error", "message": str(exc)})
    finally:
        await websocket.close()
