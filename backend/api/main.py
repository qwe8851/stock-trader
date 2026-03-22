"""
FastAPI application factory.

Startup sequence:
  1. Configure structured logging.
  2. Initialise Redis connection pool.
  3. Start the Binance ticker stream for BTCUSDT as a background task.

Shutdown sequence:
  1. Cancel the background ticker task.
  2. Close the Redis connection pool.
  3. Close the SQLAlchemy engine.
"""
import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from adapters.binance import BinanceAdapter
from api.routers import health, ohlcv, websocket
from core.config import settings
from core.logging import get_logger, setup_logging
from db.redis import close_redis, init_redis
from db.session import engine

# Bootstrap logging before anything else
setup_logging()
logger = get_logger(__name__)

# Global reference so we can cancel on shutdown
_ticker_task: asyncio.Task | None = None
_binance_adapter: BinanceAdapter | None = None


# ---------------------------------------------------------------------------
# Lifespan context manager (replaces deprecated on_event handlers)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Handle startup and shutdown logic."""
    global _ticker_task, _binance_adapter

    # ---- Startup ----
    logger.info("Starting Stock Trader API", extra={"env": settings.APP_ENV})

    # Initialise Redis
    await init_redis()

    # Start Binance real-time feed in the background
    _binance_adapter = BinanceAdapter()
    _ticker_task = asyncio.create_task(
        _run_ticker_stream(_binance_adapter, "BTCUSDT"),
        name="binance-ticker-BTCUSDT",
    )
    logger.info("Binance ticker background task started for BTCUSDT")

    yield  # Application is running

    # ---- Shutdown ----
    logger.info("Shutting down Stock Trader API...")

    if _ticker_task and not _ticker_task.done():
        _ticker_task.cancel()
        try:
            await _ticker_task
        except asyncio.CancelledError:
            pass
        logger.info("Binance ticker task cancelled")

    if _binance_adapter:
        await _binance_adapter.close()

    await close_redis()
    await engine.dispose()
    logger.info("Shutdown complete")


async def _run_ticker_stream(adapter: BinanceAdapter, symbol: str) -> None:
    """
    Wrapper that keeps the ticker stream running.
    BinanceAdapter.stream_tickers already handles reconnects internally;
    this outer wrapper catches unexpected top-level errors and logs them.
    """
    async def _noop_callback(data: dict) -> None:
        """
        The primary consumer of tick data is Redis pub/sub (handled inside
        stream_tickers). This callback is a no-op placeholder for any
        additional in-process processing (e.g. alerting, ML inference).
        """
        pass

    try:
        await adapter.stream_tickers(symbol, _noop_callback)
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

    return app


app = create_app()
