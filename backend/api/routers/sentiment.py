"""
Sentiment endpoints.

GET  /api/sentiment/{symbol}  — current sentiment score + recent news
POST /api/sentiment/{symbol}/refresh  — trigger immediate refresh (async)
"""
from fastapi import APIRouter, HTTPException

from core.logging import get_logger
from services.sentiment.aggregator import get_sentiment

logger = get_logger(__name__)
router = APIRouter(prefix="/api/sentiment", tags=["sentiment"])

SUPPORTED_SYMBOLS = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"}


@router.get("/{symbol}")
async def get_symbol_sentiment(symbol: str):
    """
    Returns the current sentiment score for a symbol.

    score: float in [-1.0, +1.0]
      +1.0 = very positive
      -1.0 = very negative
       0.0 = neutral

    label: "positive" | "negative" | "neutral"

    cached: true if served from Redis cache (< 30 min old)
    """
    sym = symbol.upper()
    if sym not in SUPPORTED_SYMBOLS:
        raise HTTPException(
            status_code=400,
            detail=f"Symbol '{sym}' not supported. Supported: {sorted(SUPPORTED_SYMBOLS)}",
        )

    try:
        result = await get_sentiment(sym)
        return result
    except Exception as exc:
        logger.error("Sentiment fetch failed", extra={"symbol": sym, "error": str(exc)})
        raise HTTPException(status_code=500, detail=f"Sentiment service error: {exc}")


@router.post("/{symbol}/refresh")
async def refresh_symbol_sentiment(symbol: str):
    """Trigger an immediate sentiment refresh for a symbol (runs in Celery)."""
    sym = symbol.upper()
    if sym not in SUPPORTED_SYMBOLS:
        raise HTTPException(status_code=400, detail=f"Symbol '{sym}' not supported")

    from tasks.sentiment_tasks import refresh_sentiment_symbol
    task = refresh_sentiment_symbol.delay(sym)
    return {"task_id": task.id, "message": f"Sentiment refresh queued for {sym}"}
