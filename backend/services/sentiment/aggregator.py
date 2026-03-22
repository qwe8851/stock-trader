"""
Sentiment aggregator.

Combines scored news items into a single composite score per symbol,
then caches the result in Redis with a 30-minute TTL.

Cache key format: sentiment:{symbol}   e.g. sentiment:BTCUSDT
Cache value: JSON with { score, items, updated_at }
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import redis.asyncio as aioredis

from core.config import settings
from core.logging import get_logger
from services.sentiment.finbert_scorer import score_items
from services.sentiment.news_fetcher import NewsItem, fetch_news

logger = get_logger(__name__)

CACHE_TTL_SECONDS = 1800   # 30 minutes
CACHE_KEY = "sentiment:{symbol}"


async def get_sentiment(symbol: str) -> dict:
    """
    Return cached sentiment for a symbol, or compute it on cache miss.

    Returns:
        {
          "symbol": str,
          "score": float,          # [-1, +1]
          "label": str,            # "positive" | "negative" | "neutral"
          "items": [...],          # scored news headlines
          "updated_at": str,       # ISO timestamp
          "cached": bool
        }
    """
    r = await _get_redis()
    cache_key = CACHE_KEY.format(symbol=symbol)

    # Check cache first
    cached = await r.get(cache_key)
    await r.aclose()
    if cached:
        data = json.loads(cached)
        data["cached"] = True
        return data

    # Cache miss — fetch and score
    return await refresh_sentiment(symbol)


async def refresh_sentiment(symbol: str) -> dict:
    """
    Fetch fresh news, score with FinBERT, aggregate, and cache.
    Called by the Celery beat task every 15 minutes.
    """
    logger.info("Refreshing sentiment", extra={"symbol": symbol})

    # 1. Fetch news
    items = await fetch_news(symbol, max_items=20)

    if not items:
        logger.warning("No news found", extra={"symbol": symbol})
        result = _empty_result(symbol)
        await _cache(symbol, result)
        return result

    # 2. Score with FinBERT (CPU, sync call — ok inside async via threadpool for prod,
    #    but fine here since Celery tasks are synchronous anyway)
    scored = score_items(items)

    # 3. Compute weighted aggregate score
    # Recent articles (index 0) get higher weight
    weights = [1.0 / (i + 1) for i in range(len(scored))]
    total_weight = sum(weights)
    composite = sum(
        (item.sentiment_score or 0.0) * w
        for item, w in zip(scored, weights)
    ) / total_weight if total_weight > 0 else 0.0

    composite = round(composite, 4)
    label = _label(composite)

    result = {
        "symbol": symbol,
        "score": composite,
        "label": label,
        "items": [
            {
                "title": item.title,
                "source": item.source,
                "url": item.url,
                "published_at": item.published_at.isoformat(),
                "sentiment_score": item.sentiment_score,
            }
            for item in scored[:10]   # return top 10 to the API
        ],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "cached": False,
    }

    await _cache(symbol, result)
    logger.info("Sentiment computed", extra={
        "symbol": symbol, "score": composite, "label": label, "articles": len(items),
    })
    return result


async def _get_redis():
    """Create a short-lived Redis connection (works in both FastAPI and Celery contexts)."""
    return await aioredis.from_url(settings.REDIS_URL, decode_responses=True)


async def _cache(symbol: str, data: dict) -> None:
    r = await _get_redis()
    cache_key = CACHE_KEY.format(symbol=symbol)
    await r.set(cache_key, json.dumps(data), ex=CACHE_TTL_SECONDS)
    await r.aclose()


def _label(score: float) -> str:
    if score >= 0.1:
        return "positive"
    if score <= -0.1:
        return "negative"
    return "neutral"


def _empty_result(symbol: str) -> dict:
    return {
        "symbol": symbol,
        "score": 0.0,
        "label": "neutral",
        "items": [],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "cached": False,
    }
