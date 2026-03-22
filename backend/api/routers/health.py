"""
Health check endpoint.
Used by Docker health checks, load balancers, and monitoring tools.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from db.session import get_db
from db.redis import get_redis_dep
from redis.asyncio import Redis

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check(
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis_dep),
) -> dict:
    """
    Returns the health status of the application and its dependencies.
    A 200 response with {"status": "ok"} means all systems are operational.
    """
    checks: dict = {"status": "ok"}

    # Database check
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"
        checks["status"] = "degraded"

    # Redis check
    try:
        await redis.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"
        checks["status"] = "degraded"

    return checks
