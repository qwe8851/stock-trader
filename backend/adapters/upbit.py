"""
Upbit exchange adapter.

Upbit은 한국의 주요 암호화폐 거래소로 KRW(원화) 마켓을 사용합니다.
Binance의 BTCUSDT 심볼과 달리 Upbit은 KRW-BTC 형식을 사용합니다.

주요 차이점:
  - 심볼 형식: KRW-BTC, KRW-ETH (USDT가 아닌 KRW)
  - 인증: JWT 방식 (HMAC-SHA512 서명)
  - WebSocket: 별도 프로토콜 (JSON 구독 메시지 전송)
  - 주문 최소 금액: 5,000 KRW

REST API: https://api.upbit.com
WebSocket: wss://api.upbit.com/websocket/v1
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from collections.abc import Callable, Awaitable
from typing import Any

import httpx

from adapters.base import BaseExchangeAdapter
from core.config import settings
from core.logging import get_logger
from db.redis import get_redis

logger = get_logger(__name__)

UPBIT_REST_URL = "https://api.upbit.com/v1"
UPBIT_WS_URL = "wss://api.upbit.com/websocket/v1"
PRICE_CHANNEL = "prices:{symbol}"

_RECONNECT_INITIAL_DELAY = 1.0
_RECONNECT_MAX_DELAY = 60.0


def _to_upbit_market(symbol: str) -> str:
    """
    Convert universal symbol to Upbit market format.

    BTCUSDT → KRW-BTC
    ETHUSDT → KRW-ETH
    SOLUSDT → KRW-SOL
    KRW-BTC → KRW-BTC  (passthrough)
    """
    if symbol.startswith("KRW-"):
        return symbol
    base = symbol.replace("USDT", "").replace("BTC", "").replace("KRW", "")
    if "USDT" in symbol:
        base = symbol[: symbol.index("USDT")]
    return f"KRW-{base.upper()}"


def _to_universal_symbol(market: str) -> str:
    """KRW-BTC → BTCUSDT (approximate — used for Redis channel naming)"""
    if market.startswith("KRW-"):
        return market[4:] + "USDT"
    return market


class UpbitAdapter(BaseExchangeAdapter):
    """
    Upbit implementation of BaseExchangeAdapter.

    Read-only mode (market data) works without API keys.
    Order operations require UPBIT_ACCESS_KEY and UPBIT_SECRET_KEY.
    """

    def __init__(self) -> None:
        self._access_key = settings.UPBIT_ACCESS_KEY
        self._secret_key = settings.UPBIT_SECRET_KEY
        self._client: httpx.AsyncClient | None = None

    @property
    def has_credentials(self) -> bool:
        return bool(self._access_key and self._secret_key)

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=UPBIT_REST_URL,
                timeout=10.0,
                headers={"Accept": "application/json"},
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    async def get_ohlcv(
        self,
        symbol: str,
        interval: str = "1m",
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """
        Fetch OHLCV candles from Upbit.

        Upbit interval mapping:
          1m  → minutes/1
          3m  → minutes/3
          5m  → minutes/5
          15m → minutes/15
          30m → minutes/30
          1h  → minutes/60
          4h  → minutes/240
          1d  → days
        """
        market = _to_upbit_market(symbol)
        upbit_interval = _map_interval(interval)
        client = self._get_client()

        try:
            resp = await client.get(
                f"/{upbit_interval}",
                params={"market": market, "count": min(limit, 200)},
            )
            resp.raise_for_status()
            raw = resp.json()
        except Exception as exc:
            logger.error("Upbit OHLCV fetch failed",
                         extra={"symbol": symbol, "error": str(exc)})
            raise

        return [_normalise_candle(c) for c in raw]

    # ------------------------------------------------------------------
    # Real-time streaming
    # ------------------------------------------------------------------

    async def stream_tickers(
        self,
        symbol: str,
        callback: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        """
        Subscribe to Upbit WebSocket candle stream and publish to Redis.

        Upbit WebSocket 프로토콜:
          1. 연결 후 구독 메시지 전송
          2. 응답으로 ticker/candle 데이터 수신
        """
        import websockets

        market = _to_upbit_market(symbol)
        delay = _RECONNECT_INITIAL_DELAY

        while True:
            try:
                async with websockets.connect(
                    UPBIT_WS_URL,
                    extra_headers={"User-Agent": "StockTrader/1.0"},
                ) as ws:
                    # Subscribe to candle data
                    subscribe_msg = json.dumps([
                        {"ticket": str(uuid.uuid4())},
                        {"type": "candle.1m", "codes": [market]},
                        {"format": "SIMPLE"},
                    ])
                    await ws.send(subscribe_msg)
                    logger.info("Upbit WebSocket connected", extra={"market": market})
                    delay = _RECONNECT_INITIAL_DELAY

                    while True:
                        raw = await ws.recv()
                        if isinstance(raw, bytes):
                            data = json.loads(raw.decode("utf-8"))
                        else:
                            data = json.loads(raw)

                        candle = _normalise_ws_candle(data, symbol)
                        if candle is None:
                            continue

                        # Publish to Redis
                        try:
                            redis = get_redis()
                            channel = PRICE_CHANNEL.format(symbol=symbol)
                            await redis.publish(channel, json.dumps(candle))
                        except Exception as redis_exc:
                            logger.warning("Redis publish failed",
                                           extra={"error": str(redis_exc)})

                        await callback(candle)

            except asyncio.CancelledError:
                logger.info("Upbit stream cancelled", extra={"symbol": symbol})
                raise
            except Exception as exc:
                logger.error("Upbit WebSocket error - reconnecting",
                             extra={"symbol": symbol, "error": str(exc), "delay": delay})
                await asyncio.sleep(delay)
                delay = min(delay * 2, _RECONNECT_MAX_DELAY)

    # ------------------------------------------------------------------
    # Order management (requires API keys)
    # ------------------------------------------------------------------

    def _require_credentials(self) -> None:
        if not self.has_credentials:
            raise RuntimeError(
                "Upbit API credentials required. "
                "Set UPBIT_ACCESS_KEY and UPBIT_SECRET_KEY in your environment."
            )

    def _auth_header(self, query_params: dict | None = None) -> dict:
        """Generate JWT Authorization header for Upbit private endpoints."""
        import jwt as pyjwt

        payload: dict[str, Any] = {
            "access_key": self._access_key,
            "nonce": str(uuid.uuid4()),
        }
        if query_params:
            import urllib.parse
            query_string = urllib.parse.urlencode(query_params).encode()
            m = hashlib.sha512()
            m.update(query_string)
            payload["query_hash"] = m.hexdigest()
            payload["query_hash_alg"] = "SHA512"

        token = pyjwt.encode(payload, self._secret_key, algorithm="HS256")
        return {"Authorization": f"Bearer {token}"}

    async def place_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float | None = None,
    ) -> dict[str, Any]:
        self._require_credentials()

        if settings.LIVE_TRADING_ENABLED is False:
            raise RuntimeError("Live trading disabled. Set LIVE_TRADING_ENABLED=true.")

        market = _to_upbit_market(symbol)
        # Upbit side: "bid" = buy, "ask" = sell
        upbit_side = "bid" if side.upper() == "BUY" else "ask"

        params: dict[str, Any] = {
            "market": market,
            "side": upbit_side,
            "ord_type": "limit" if price else "market",
        }

        if price:
            params["price"] = str(price)
            params["volume"] = str(quantity)
        else:
            # Market order: specify price (total KRW amount) for bid
            if upbit_side == "bid":
                # For market buy: specify price as total KRW to spend
                params["price"] = str(int(quantity))  # quantity in KRW for market buy
                params["ord_type"] = "price"
            else:
                params["volume"] = str(quantity)
                params["ord_type"] = "market"

        client = self._get_client()
        headers = self._auth_header(params)

        try:
            resp = await client.post("/orders", json=params, headers=headers)
            resp.raise_for_status()
            result = resp.json()
            logger.info("Upbit order placed", extra={
                "uuid": result.get("uuid"), "market": market, "side": upbit_side,
            })
            return result
        except Exception as exc:
            logger.error("Upbit order failed", extra={"error": str(exc)})
            raise

    async def cancel_order(self, symbol: str, order_id: str) -> dict[str, Any]:
        self._require_credentials()
        client = self._get_client()
        params = {"uuid": order_id}
        headers = self._auth_header(params)
        resp = await client.delete("/order", params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def get_balance(self) -> dict[str, Any]:
        self._require_credentials()
        client = self._get_client()
        headers = self._auth_header()
        resp = await client.get("/accounts", headers=headers)
        resp.raise_for_status()
        accounts = resp.json()
        return {
            acc["currency"]: {
                "free": float(acc["balance"]),
                "locked": float(acc["locked"]),
            }
            for acc in accounts
            if float(acc["balance"]) > 0 or float(acc["locked"]) > 0
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _map_interval(interval: str) -> str:
    """Map universal interval string to Upbit candle endpoint path."""
    mapping = {
        "1m": "candles/minutes/1",
        "3m": "candles/minutes/3",
        "5m": "candles/minutes/5",
        "15m": "candles/minutes/15",
        "30m": "candles/minutes/30",
        "1h": "candles/minutes/60",
        "4h": "candles/minutes/240",
        "1d": "candles/days",
        "1w": "candles/weeks",
    }
    return mapping.get(interval, "candles/minutes/1")


def _normalise_candle(c: dict) -> dict[str, Any]:
    """Normalise Upbit REST candle response to universal format."""
    return {
        "time": int(c["timestamp"]),
        "open": float(c["opening_price"]),
        "high": float(c["high_price"]),
        "low": float(c["low_price"]),
        "close": float(c["trade_price"]),
        "volume": float(c["candle_acc_trade_volume"]),
        "close_time": int(c["timestamp"]),
        "quote_volume": float(c.get("candle_acc_trade_price", 0)),
        "num_trades": 0,
    }


def _normalise_ws_candle(data: dict, symbol: str) -> dict[str, Any] | None:
    """Normalise Upbit WebSocket candle message to universal format."""
    tp = data.get("ty", "")
    if not tp.startswith("candle"):
        return None
    try:
        return {
            "time": int(data.get("tms", 0)),
            "open": float(data.get("op", 0)),
            "high": float(data.get("hp", 0)),
            "low": float(data.get("lp", 0)),
            "close": float(data.get("tp", 0)),
            "volume": float(data.get("tv", 0)),
            "close_time": int(data.get("tms", 0)),
            "quote_volume": float(data.get("atpv", 0)),
            "num_trades": 0,
            "is_closed": False,
            "symbol": symbol,
            "interval": "1m",
            "event_time": int(data.get("tms", 0)),
        }
    except Exception:
        return None
