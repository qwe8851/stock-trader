"""
FastAPI application factory.

Startup sequence:
  1. Configure structured logging.
  2. Initialise Redis connection pool.
  3. Select exchange adapter (Binance or Upbit) from ACTIVE_EXCHANGE setting.
  4. Start the ticker stream for BTCUSDT (Binance) or KRW-BTC (Upbit).
  5. Start the TradingEngine background loop.

Shutdown sequence:
  1. Cancel background tasks.
  2. Close the Redis connection pool.
  3. Close the SQLAlchemy engine.
"""
import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from adapters.base import BaseExchangeAdapter
from adapters.binance import BinanceAdapter
from adapters.upbit import UpbitAdapter
from api.routers import (
    analytics, api_keys, auth, backtest, exchange_settings, health, ohlcv,
    orders, portfolio, sentiment, strategies, websocket,
)
from core.config import settings
from core.logging import get_logger, setup_logging
from db.redis import close_redis, init_redis
from db.session import engine as db_engine
from engine.trading_engine import engine as trading_engine

# Bootstrap logging before anything else
setup_logging()
logger = get_logger(__name__)

# Global references for graceful shutdown
_ticker_task: asyncio.Task | None = None
_trading_task: asyncio.Task | None = None
_active_adapter: BaseExchangeAdapter | None = None


def _build_adapter() -> tuple[BaseExchangeAdapter, str, str]:
    """
    Instantiate the adapter for the configured exchange.

    Returns (adapter, exchange_name, default_symbol).
    - Binance: streams BTCUSDT
    - Upbit:   streams KRW-BTC
    """
    exchange = settings.ACTIVE_EXCHANGE.lower()
    if exchange == "upbit":
        return UpbitAdapter(), "upbit", "KRW-BTC"
    return BinanceAdapter(), "binance", "BTCUSDT"


# ---------------------------------------------------------------------------
# Lifespan context manager
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Handle startup and shutdown logic."""
    global _ticker_task, _trading_task, _active_adapter

    # ---- Startup ----
    logger.info("Starting Stock Trader API",
                extra={"env": settings.APP_ENV, "exchange": settings.ACTIVE_EXCHANGE})

    await init_redis()

    # Build exchange adapter
    _active_adapter, exchange_name, default_symbol = _build_adapter()
    trading_engine.set_adapter(_active_adapter, exchange_name)

    # Start price feed
    _ticker_task = asyncio.create_task(
        _run_ticker_stream(_active_adapter, default_symbol),
        name=f"{exchange_name}-ticker-{default_symbol}",
    )
    logger.info("Ticker background task started",
                extra={"exchange": exchange_name, "symbol": default_symbol})

    # Start trading engine
    _trading_task = asyncio.create_task(
        trading_engine.run(),
        name="trading-engine",
    )
    logger.info("Trading engine background task started")

    yield  # ← application is running

    # ---- Shutdown ----
    logger.info("Shutting down Stock Trader API...")

    if _trading_task and not _trading_task.done():
        _trading_task.cancel()
        try:
            await _trading_task
        except asyncio.CancelledError:
            pass

    if _ticker_task and not _ticker_task.done():
        _ticker_task.cancel()
        try:
            await _ticker_task
        except asyncio.CancelledError:
            pass

    if _active_adapter:
        await _active_adapter.close()

    await close_redis()
    await db_engine.dispose()
    logger.info("Shutdown complete")


async def _run_ticker_stream(adapter: BaseExchangeAdapter, symbol: str) -> None:
    """
    Wrap stream_tickers so top-level errors are logged rather than silently lost.
    The adapter itself handles reconnects internally.
    """
    async def _noop(data: dict) -> None:
        pass

    try:
        await adapter.stream_tickers(symbol, _noop)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.error(
            "Ticker stream task exited unexpectedly",
            extra={"symbol": symbol, "error": str(exc)},
        )


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    app = FastAPI(
        title="Stock Trader API",
        description="Automated cryptocurrency trading bot",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS - allow all origins in development; tighten in production
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(health.router)
    app.include_router(ohlcv.router)
    app.include_router(websocket.router)
    app.include_router(strategies.router)
    app.include_router(orders.router)
    app.include_router(portfolio.router)
    app.include_router(backtest.router)
    app.include_router(sentiment.router)
    app.include_router(exchange_settings.router)
    app.include_router(analytics.router)
    app.include_router(auth.router)
    app.include_router(api_keys.router)

    return app


app = create_app()
