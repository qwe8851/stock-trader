"""
Analytics & notification Celery tasks.

Tasks:
  save_portfolio_snapshot  — 매 1시간 포트폴리오 가치를 DB에 기록 (Beat)
  send_daily_summary_task  — 매일 오전 9시 KST 일일 성과 요약 Telegram 발송 (Beat)
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from celery import shared_task

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)


@shared_task(name="tasks.save_portfolio_snapshot")
def save_portfolio_snapshot() -> dict:
    """
    현재 포트폴리오 가치를 portfolio_snapshots 테이블에 저장합니다.
    Celery Beat가 1시간 간격으로 실행합니다.
    """
    return asyncio.run(_save_snapshot_async())


async def _save_snapshot_async() -> dict:
    import redis.asyncio as aioredis
    import sqlalchemy as sa
    from db.session import AsyncSessionLocal as async_session

    # 엔진의 현재 상태를 Redis에서 읽어옴
    r = await aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    raw = await r.get("engine:portfolio_snapshot")
    await r.aclose()

    if not raw:
        logger.info("No portfolio snapshot in Redis — skipping DB write")
        return {"saved": False}

    data = json.loads(raw)
    now = datetime.now(timezone.utc)

    async with async_session() as session:
        await session.execute(
            sa.text(
                """
                INSERT INTO portfolio_snapshots
                    (snapshot_time, total_value_usd, available_usd,
                     open_positions, exchange, mode)
                VALUES
                    (:ts, :tv, :av, :op, :ex, :mode)
                """
            ),
            {
                "ts": now,
                "tv": data.get("total_value_usd", 0),
                "av": data.get("available_usd", 0),
                "op": data.get("open_positions", 0),
                "ex": data.get("exchange", settings.ACTIVE_EXCHANGE),
                "mode": "PAPER" if settings.PAPER_TRADING_MODE else "LIVE",
            },
        )
        await session.commit()

    logger.info("Portfolio snapshot saved", extra={"value": data.get("total_value_usd")})
    return {"saved": True, "value": data.get("total_value_usd")}


@shared_task(name="tasks.send_daily_summary")
def send_daily_summary_task() -> None:
    """
    일일 성과 요약을 Telegram으로 발송합니다.
    Celery Beat가 매일 09:00 KST (00:00 UTC)에 실행합니다.
    """
    if not settings.telegram_enabled:
        logger.info("Telegram not configured — skipping daily summary")
        return
    asyncio.run(_daily_summary_async())


async def _daily_summary_async() -> None:
    import redis.asyncio as aioredis
    from engine.trading_engine import engine as trading_engine
    from services.analytics.performance import compute_overall_performance
    from services.notifications.telegram import notify_daily_summary

    # Redis에서 포트폴리오 스냅샷 읽기
    r = await aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    raw = await r.get("engine:portfolio_snapshot")
    await r.aclose()

    if raw:
        snap = json.loads(raw)
        portfolio_value = snap.get("total_value_usd", settings.PAPER_INITIAL_BALANCE)
        daily_start = snap.get("daily_start_value", settings.PAPER_INITIAL_BALANCE)
    else:
        portfolio_value = settings.PAPER_INITIAL_BALANCE
        daily_start = settings.PAPER_INITIAL_BALANCE

    daily_pnl = portfolio_value - daily_start
    daily_pnl_pct = daily_pnl / daily_start * 100 if daily_start > 0 else 0

    # 주문 이력에서 성과 지표 계산
    orders = trading_engine.order_manager.get_orders(limit=500)
    overall = compute_overall_performance(orders, settings.PAPER_INITIAL_BALANCE)

    summary = {
        "portfolio_value": portfolio_value,
        "daily_pnl": daily_pnl,
        "daily_pnl_pct": daily_pnl_pct,
        "total_trades": overall["total_trades"],
        "win_rate": overall["win_rate"],
        "exchange": settings.ACTIVE_EXCHANGE,
    }

    await notify_daily_summary(summary)
    logger.info("Daily summary sent via Telegram")
