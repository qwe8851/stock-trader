"""
OHLCV REST endpoints - fetch historical candlestick data.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.binance import BinanceAdapter
from db.models.ohlcv import OHLCV
from db.session import get_db
from core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/ohlcv", tags=["ohlcv"])


@router.get("/{symbol}")
async def get_ohlcv(
    symbol: str,
    interval: Annotated[str, Query(description="Candle interval, e.g. 1m, 5m, 1h")] = "1m",
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> dict:
    """
    Fetch OHLCV data directly from Binance REST API.

    Returns the last ``limit`` candles for the given symbol and interval.
    This endpoint is used to seed the chart with historical data on page load.
    """
    sym = symbol.upper()
    try:
        adapter = BinanceAdapter()
        candles = await adapter.get_ohlcv(sym, interval=interval, limit=limit)
        return {"symbol": sym, "interval": interval, "data": candles}
    except Exception as exc:
        logger.error(
            "OHLCV fetch failed",
            extra={"symbol": sym, "error": str(exc)},
        )
        raise
