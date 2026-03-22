"""
Sentiment-enhanced RSI strategy.

Combines the RSI crossover signal with a FinBERT sentiment gate:
  - BUY  only when RSI < oversold  AND  sentiment score > sentiment_threshold
  - SELL only when RSI > overbought AND  sentiment score < -sentiment_threshold
  - Otherwise HOLD

The sentiment score is read from the Redis cache (set by the Celery beat task).
Falls back to RSI-only behaviour when no sentiment data is available.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from core.logging import get_logger
from engine.strategies.base import BaseStrategy, Candle, Signal, SignalAction
from engine.strategies.rsi_strategy import _calc_rsi

logger = get_logger(__name__)

SENTIMENT_CACHE_KEY = "sentiment:{symbol}"


def _read_sentiment_sync(symbol: str) -> float | None:
    """
    Read the cached sentiment score for a symbol from Redis.
    Uses a synchronous redis call to avoid async complexity inside
    the synchronous strategy evaluate path.
    Returns None if no data is cached yet.
    """
    try:
        import redis as sync_redis
        from core.config import settings
        r = sync_redis.from_url(settings.REDIS_URL, decode_responses=True)
        raw = r.get(SENTIMENT_CACHE_KEY.format(symbol=symbol))
        r.close()
        if raw:
            data = json.loads(raw)
            return float(data.get("score", 0.0))
    except Exception as exc:
        logger.warning("Could not read sentiment from Redis", extra={"error": str(exc)})
    return None


class SentimentStrategy(BaseStrategy):
    """
    Config keys:
      period               (int)   RSI period, default 14
      oversold             (float) RSI buy threshold, default 30
      overbought           (float) RSI sell threshold, default 70
      sentiment_threshold  (float) Min abs sentiment to act, default 0.1
                                   Set to 0.0 to ignore sentiment gate
    """

    @property
    def name(self) -> str:
        return "SENTIMENT"

    @property
    def min_candles(self) -> int:
        return self.config.get("period", 14) + 2

    def _evaluate(self, candles: list[Candle]) -> Signal:
        period: int = self.config.get("period", 14)
        oversold: float = self.config.get("oversold", 30.0)
        overbought: float = self.config.get("overbought", 70.0)
        threshold: float = self.config.get("sentiment_threshold", 0.1)

        closes = [c.close for c in candles]
        rsi = _calc_rsi(closes, period)
        prev_rsi = _calc_rsi(closes[:-1], period) if len(closes) > period + 1 else rsi

        sentiment = _read_sentiment_sync(self.symbol)
        sentiment_available = sentiment is not None
        sentiment_val = sentiment if sentiment is not None else 0.0

        meta = {
            "rsi": round(rsi, 2),
            "sentiment": round(sentiment_val, 4) if sentiment_available else None,
            "sentiment_available": sentiment_available,
        }

        # --- BUY signal ---
        if prev_rsi >= oversold > rsi:
            # RSI oversold crossover confirmed — now check sentiment gate
            if not sentiment_available or threshold == 0.0:
                # No sentiment data: fall back to pure RSI
                confidence = min(1.0, (oversold - rsi) / oversold)
                return Signal(
                    action=SignalAction.BUY,
                    symbol=self.symbol,
                    confidence=confidence,
                    reason=f"RSI oversold ({rsi:.1f}) — sentiment unavailable, RSI-only",
                    metadata=meta,
                )
            if sentiment_val >= threshold:
                confidence = min(1.0, (oversold - rsi) / oversold * (sentiment_val + 1) / 2)
                return Signal(
                    action=SignalAction.BUY,
                    symbol=self.symbol,
                    confidence=confidence,
                    reason=(
                        f"RSI oversold ({rsi:.1f}) + positive sentiment ({sentiment_val:+.3f})"
                    ),
                    metadata=meta,
                )
            else:
                return Signal(
                    action=SignalAction.HOLD,
                    symbol=self.symbol,
                    reason=f"RSI oversold but sentiment too low ({sentiment_val:+.3f} < {threshold})",
                    metadata=meta,
                )

        # --- SELL signal ---
        if prev_rsi <= overbought < rsi:
            if not sentiment_available or threshold == 0.0:
                confidence = min(1.0, (rsi - overbought) / (100 - overbought))
                return Signal(
                    action=SignalAction.SELL,
                    symbol=self.symbol,
                    confidence=confidence,
                    reason=f"RSI overbought ({rsi:.1f}) — sentiment unavailable, RSI-only",
                    metadata=meta,
                )
            if sentiment_val <= -threshold:
                confidence = min(1.0, (rsi - overbought) / (100 - overbought))
                return Signal(
                    action=SignalAction.SELL,
                    symbol=self.symbol,
                    confidence=confidence,
                    reason=(
                        f"RSI overbought ({rsi:.1f}) + negative sentiment ({sentiment_val:+.3f})"
                    ),
                    metadata=meta,
                )
            else:
                return Signal(
                    action=SignalAction.HOLD,
                    symbol=self.symbol,
                    reason=f"RSI overbought but sentiment not negative ({sentiment_val:+.3f})",
                    metadata=meta,
                )

        return Signal(
            action=SignalAction.HOLD,
            symbol=self.symbol,
            reason=f"RSI neutral ({rsi:.1f}), sentiment ({sentiment_val:+.3f})",
            metadata=meta,
        )
