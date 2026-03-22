"""
Celery tasks for sentiment analysis.

Scheduled task: runs every 15 minutes via Celery beat.
Fetches news for all tracked symbols, scores with FinBERT,
and caches results in Redis.
"""
import asyncio

from celery import shared_task

from core.logging import get_logger

logger = get_logger(__name__)

TRACKED_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]


@shared_task(name="tasks.refresh_all_sentiment", bind=True, max_retries=2)
def refresh_all_sentiment(self) -> dict:
    """
    Refresh sentiment for all tracked symbols.
    Runs every 15 minutes via Celery beat schedule.
    """
    results = {}
    for symbol in TRACKED_SYMBOLS:
        try:
            result = asyncio.run(_refresh_one(symbol))
            results[symbol] = {
                "score": result.get("score"),
                "label": result.get("label"),
                "articles": len(result.get("items", [])),
            }
            logger.info("Sentiment refreshed", extra={
                "symbol": symbol,
                "score": result.get("score"),
                "label": result.get("label"),
            })
        except Exception as exc:
            logger.error("Sentiment refresh failed", extra={
                "symbol": symbol, "error": str(exc),
            })
            results[symbol] = {"error": str(exc)}
    return results


@shared_task(name="tasks.refresh_sentiment_symbol", bind=True, max_retries=2)
def refresh_sentiment_symbol(self, symbol: str) -> dict:
    """Refresh sentiment for a single symbol (triggered on-demand from API)."""
    try:
        result = asyncio.run(_refresh_one(symbol))
        return result
    except Exception as exc:
        logger.error("On-demand sentiment refresh failed", extra={
            "symbol": symbol, "error": str(exc),
        })
        raise self.retry(exc=exc, countdown=5)


async def _refresh_one(symbol: str) -> dict:
    from services.sentiment.aggregator import refresh_sentiment
    return await refresh_sentiment(symbol)
