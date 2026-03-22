"""
Analytics API.

Endpoints:
  GET /api/analytics/performance   — 전략별 성과 지표
  GET /api/analytics/pnl-history   — P&L 스냅샷 이력 (DB)
  GET /api/analytics/summary       — 전체 성과 요약
"""
from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Query

from core.config import settings
from db.session import async_session
from engine.trading_engine import engine as trading_engine
from services.analytics.performance import (
    compute_overall_performance,
    compute_strategy_performance,
)

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/performance")
async def get_performance() -> list[dict[str, Any]]:
    """전략별 성과 지표를 반환합니다."""
    orders = trading_engine.order_manager.get_orders(limit=1000)
    return compute_strategy_performance(orders, settings.PAPER_INITIAL_BALANCE)


@router.get("/summary")
async def get_summary() -> dict[str, Any]:
    """전체 (전략 합산) 성과 요약을 반환합니다."""
    status = trading_engine.get_status()
    orders = trading_engine.order_manager.get_orders(limit=1000)
    overall = compute_overall_performance(orders, settings.PAPER_INITIAL_BALANCE)
    return {
        **overall,
        "portfolio_value": status["portfolio"]["total_value_usd"],
        "available_usd": status["portfolio"]["available_usd"],
        "exchange": status["exchange"],
        "paper_mode": status["paper_mode"],
    }


@router.get("/pnl-history")
async def get_pnl_history(
    limit: int = Query(default=168, ge=1, le=720),  # 기본 7일 (168시간)
) -> list[dict[str, Any]]:
    """
    포트폴리오 가치 이력을 반환합니다.

    DB에 스냅샷이 없을 경우 현재 값만 반환합니다.
    Celery Beat가 1시간마다 스냅샷을 저장합니다.
    """
    async with async_session() as session:
        result = await session.execute(
            sa.text(
                """
                SELECT snapshot_time, total_value_usd, available_usd,
                       open_positions, exchange, mode
                FROM portfolio_snapshots
                ORDER BY snapshot_time DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        )
        rows = result.fetchall()

    if not rows:
        # DB에 데이터 없으면 현재 값으로 단건 반환
        status = trading_engine.get_status()
        from datetime import datetime, timezone
        return [{
            "time": datetime.now(timezone.utc).isoformat(),
            "total_value_usd": status["portfolio"]["total_value_usd"],
            "available_usd": status["portfolio"]["available_usd"],
            "open_positions": status["portfolio"]["open_positions"],
        }]

    return [
        {
            "time": row.snapshot_time.isoformat(),
            "total_value_usd": row.total_value_usd,
            "available_usd": row.available_usd,
            "open_positions": row.open_positions,
        }
        for row in reversed(rows)   # 오름차순으로 반환
    ]
