"""
Exchange & trading-mode settings API.

Endpoints:
  GET  /api/settings          — current exchange, trading mode, credential status
  POST /api/settings/exchange — switch active exchange (runtime, no restart needed)
  POST /api/settings/live-trading — toggle LIVE_TRADING_ENABLED at runtime

⚠️  Runtime exchange switch restarts the ticker stream for the new exchange.
    The change does NOT persist across process restarts — update .env for that.
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from adapters.binance import BinanceAdapter
from adapters.upbit import UpbitAdapter
from core.config import settings
from core.logging import get_logger
from engine.trading_engine import engine as trading_engine

router = APIRouter(prefix="/api/settings", tags=["settings"])
logger = get_logger(__name__)

# Module-level ref so we can cancel on exchange switch
_ticker_task: asyncio.Task | None = None


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ExchangeSwitchRequest(BaseModel):
    exchange: str   # "binance" | "upbit"


class LiveTradingRequest(BaseModel):
    enabled: bool
    confirm: bool = False   # must be True to activate live trading


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _credential_status() -> dict[str, Any]:
    return {
        "binance": {
            "has_credentials": settings.has_binance_credentials,
            "testnet": settings.BINANCE_TESTNET,
        },
        "upbit": {
            "has_credentials": settings.has_upbit_credentials,
        },
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("")
async def get_settings() -> dict[str, Any]:
    """Return the current trading configuration."""
    status = trading_engine.get_status()
    return {
        "exchange": status["exchange"],
        "paper_mode": status["paper_mode"],
        "live_trading_enabled": status["live_trading_enabled"],
        "risk_halted": status["risk_halted"],
        "credentials": _credential_status(),
    }


@router.post("/exchange")
async def switch_exchange(body: ExchangeSwitchRequest) -> dict[str, Any]:
    """
    Switch the active exchange at runtime.

    - Stops the current ticker stream.
    - Starts a new stream for the selected exchange.
    - Injects the new adapter into the TradingEngine.
    """
    global _ticker_task

    exchange = body.exchange.lower()
    if exchange not in ("binance", "upbit"):
        raise HTTPException(400, "exchange must be 'binance' or 'upbit'")

    if exchange == "upbit" and not settings.has_upbit_credentials:
        raise HTTPException(
            400,
            "Upbit API keys not configured. "
            "Set UPBIT_ACCESS_KEY and UPBIT_SECRET_KEY in your environment.",
        )

    # Cancel existing ticker task
    if _ticker_task and not _ticker_task.done():
        _ticker_task.cancel()
        try:
            await _ticker_task
        except asyncio.CancelledError:
            pass

    # Build new adapter
    if exchange == "upbit":
        adapter = UpbitAdapter()
        default_symbol = "KRW-BTC"
    else:
        adapter = BinanceAdapter()
        default_symbol = "BTCUSDT"

    trading_engine.set_adapter(adapter, exchange)

    async def _noop(data: dict) -> None:
        pass

    _ticker_task = asyncio.create_task(
        adapter.stream_tickers(default_symbol, _noop),
        name=f"{exchange}-ticker-{default_symbol}",
    )

    logger.info("Exchange switched", extra={"exchange": exchange, "symbol": default_symbol})
    return {"exchange": exchange, "symbol": default_symbol, "status": "streaming"}


@router.post("/live-trading")
async def toggle_live_trading(body: LiveTradingRequest) -> dict[str, Any]:
    """
    Enable or disable live trading mode at runtime.

    Enabling live trading requires:
      1. body.confirm = true  (explicit user confirmation)
      2. The current exchange adapter has valid API credentials
      3. LIVE_TRADING_ENABLED environment flag (acts as a hard gate)

    ⚠️  This endpoint modifies a runtime flag only. It does NOT override the
        LIVE_TRADING_ENABLED environment variable. If the env var is false,
        live orders will still be blocked in OrderManager regardless.
    """
    if body.enabled:
        if not body.confirm:
            raise HTTPException(
                400,
                "Set confirm=true to acknowledge that real money will be used.",
            )

        if not settings.LIVE_TRADING_ENABLED:
            raise HTTPException(
                403,
                "LIVE_TRADING_ENABLED is not set in the environment. "
                "Set LIVE_TRADING_ENABLED=true in your .env file to allow live trading.",
            )

        exchange = trading_engine._exchange_name
        if exchange == "binance" and not settings.has_binance_credentials:
            raise HTTPException(
                400,
                "Binance API credentials required for live trading. "
                "Set BINANCE_API_KEY and BINANCE_SECRET_KEY in your environment.",
            )
        if exchange == "upbit" and not settings.has_upbit_credentials:
            raise HTTPException(
                400,
                "Upbit API credentials required for live trading. "
                "Set UPBIT_ACCESS_KEY and UPBIT_SECRET_KEY in your environment.",
            )

    # Mutate the runtime setting (config is an lru_cache'd singleton)
    settings.__dict__["PAPER_TRADING_MODE"] = not body.enabled
    logger.info(
        "Live trading mode changed",
        extra={"live": body.enabled, "paper": not body.enabled},
    )

    return {
        "live_trading_enabled": settings.LIVE_TRADING_ENABLED,
        "paper_mode": settings.PAPER_TRADING_MODE,
    }
