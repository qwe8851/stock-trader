"""
News fetcher — collects crypto headlines from multiple sources.

Sources (in priority order):
  1. Crypto RSS feeds (CoinDesk, CoinTelegraph, Decrypt) — no API key needed
  2. NewsAPI — optional, requires NEWSAPI_KEY in .env

Each article is normalised to a NewsItem dataclass.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone

import feedparser
import httpx

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)

# Reliable crypto RSS feeds (no auth needed, properly serve RSS to bots)
RSS_SOURCES = [
    {"name": "CoinDesk",      "url": "https://feeds.feedburner.com/CoinDesk"},
    {"name": "CoinTelegraph", "url": "https://cointelegraph.com/rss"},
    {"name": "Decrypt",       "url": "https://decrypt.co/feed"},
]

# Keywords to filter articles relevant to each symbol
SYMBOL_KEYWORDS: dict[str, list[str]] = {
    "BTCUSDT": ["bitcoin", "btc"],
    "ETHUSDT": ["ethereum", "eth", "ether"],
    "SOLUSDT": ["solana", "sol"],
    "BNBUSDT": ["binance", "bnb"],
}

NEWSAPI_URL = "https://newsapi.org/v2/everything"

RSS_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; StockTraderBot/1.0; +https://github.com)"}


@dataclass
class NewsItem:
    title: str
    source: str
    url: str
    published_at: datetime
    symbol: str
    # Unique hash to deduplicate across fetches
    uid: str = field(init=False)
    # Sentiment score filled in by FinBERTScorer
    sentiment_score: float | None = None

    def __post_init__(self) -> None:
        self.uid = hashlib.md5(self.url.encode()).hexdigest()


async def fetch_news(symbol: str, max_items: int = 30) -> list[NewsItem]:
    """
    Fetch recent news for a given symbol from all available sources.
    Filters articles by symbol-specific keywords.
    Returns deduplicated list sorted by publish time (newest first).
    """
    items: list[NewsItem] = []
    seen: set[str] = set()
    keywords = SYMBOL_KEYWORDS.get(symbol.upper(), [symbol.replace("USDT", "").lower()])

    # Source 1: RSS feeds (always available)
    rss_items = await _fetch_all_rss(keywords, max_items)
    for item in rss_items:
        item.symbol = symbol
        if item.uid not in seen:
            items.append(item)
            seen.add(item.uid)

    # Source 2: NewsAPI (optional — skip gracefully if no key)
    if settings.NEWSAPI_KEY:
        try:
            newsapi_items = await _fetch_newsapi(symbol, max_items)
            for item in newsapi_items:
                if item.uid not in seen:
                    items.append(item)
                    seen.add(item.uid)
        except Exception as exc:
            logger.warning("NewsAPI fetch failed", extra={"error": str(exc)})

    items.sort(key=lambda x: x.published_at, reverse=True)
    logger.info("News fetched", extra={"symbol": symbol, "count": len(items)})
    return items[:max_items]


async def _fetch_all_rss(keywords: list[str], max_items: int) -> list[NewsItem]:
    """Fetch from all RSS sources and filter by keyword relevance."""
    all_items: list[NewsItem] = []

    async with httpx.AsyncClient(timeout=10.0, headers=RSS_HEADERS) as client:
        for source in RSS_SOURCES:
            try:
                resp = await client.get(source["url"], follow_redirects=True)
                resp.raise_for_status()
                feed = feedparser.parse(resp.text)

                for entry in feed.entries:
                    title = entry.get("title", "")
                    link = entry.get("link", "")
                    if not title:
                        continue

                    # Keyword filter — keep articles mentioning the coin
                    title_lower = title.lower()
                    if not any(kw.lower() in title_lower for kw in keywords):
                        continue

                    published = _parse_rss_date(entry.get("published", ""))
                    all_items.append(NewsItem(
                        title=title,
                        source=source["name"],
                        url=link,
                        published_at=published,
                        symbol="",  # set by caller
                    ))
            except Exception as exc:
                logger.warning("RSS fetch failed", extra={
                    "source": source["name"], "error": str(exc),
                })

    return all_items[:max_items]


async def _fetch_newsapi(symbol: str, max_items: int) -> list[NewsItem]:
    """Fetch from NewsAPI using keyword search."""
    keywords = SYMBOL_KEYWORDS.get(symbol, [symbol.replace("USDT", "")])
    query = " OR ".join(f'"{kw}"' for kw in keywords[:2])

    params = {
        "q": query,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": max_items,
        "apiKey": settings.NEWSAPI_KEY,
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(NEWSAPI_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    items: list[NewsItem] = []
    for article in data.get("articles", []):
        try:
            published = datetime.fromisoformat(
                article["publishedAt"].replace("Z", "+00:00")
            )
            items.append(NewsItem(
                title=article.get("title", ""),
                source=article.get("source", {}).get("name", "NewsAPI"),
                url=article.get("url", ""),
                published_at=published,
                symbol=symbol,
            ))
        except Exception:
            continue
    return items


def _parse_rss_date(date_str: str) -> datetime:
    """Parse RFC 2822 RSS date strings."""
    if not date_str:
        return datetime.now(timezone.utc)
    try:
        import email.utils
        parsed = email.utils.parsedate_to_datetime(date_str)
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    except Exception:
        return datetime.now(timezone.utc)
