"""
Risk management endpoints.

GET  /api/risk/metrics        — Kelly, VaR, drawdown, per-strategy stats
GET  /api/risk/events         — last N risk events (halts, pauses, resumes)
POST /api/risk/config         — update RiskConfig at runtime
POST /api/risk/resume         — clear global halt
POST /api/risk/resume/{name}  — clear per-strategy pause
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from core.logging import get_logger
from engine.trading_engine import engine as trading_engine

logger = get_logger(__name__)
router = APIRouter(prefix="/api/risk", tags=["risk"])


class RiskConfigUpdate(BaseModel):
    max_position_pct: float | None = Field(None, gt=0, le=1)
    daily_loss_limit_pct: float | None = Field(None, gt=0, le=1)
    max_open_positions: int | None = Field(None, ge=1, le=20)
    use_kelly: bool | None = None
    half_kelly: bool | None = None
    kelly_lookback: int | None = Field(None, ge=10, le=500)
    strategy_drawdown_limit_pct: float | None = Field(None, gt=0, le=1)
    min_profit_pct: float | None = Field(None, ge=0, le=0.1)
    fee_pct: float | None = Field(None, ge=0, le=0.01)


@router.get("/metrics")
async def get_risk_metrics():
    """Full risk metrics snapshot."""
    from engine.trading_engine import engine

    status = engine.get_status()
    portfolio = status["portfolio"]
    orders = engine.order_manager.get_orders(500)

    from engine.risk_manager import PortfolioSnapshot
    snap = PortfolioSnapshot(
        total_value_usd=portfolio["total_value_usd"],
        open_positions=portfolio["open_positions"],
        daily_start_value=portfolio["daily_start_value"],
    )

    metrics = engine.risk_manager.get_metrics(snap, orders)
    return metrics


@router.get("/events")
async def get_risk_events(n: int = 50):
    """Last N risk events (halts, pauses, resumes)."""
    return {"events": trading_engine.risk_manager.get_events(n)}


@router.post("/config")
async def update_risk_config(body: RiskConfigUpdate):
    """Update RiskConfig fields at runtime without restarting."""
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        return {"updated": False, "message": "No fields provided"}

    trading_engine.risk_manager.update_config(**updates)
    logger.info("Risk config updated via API", extra={"updates": updates})
    return {"updated": True, "changes": updates}


@router.post("/resume")
async def resume_trading():
    """Clear the global halt (circuit breaker)."""
    trading_engine.risk_manager.resume()
    return {"resumed": True}


@router.post("/resume/{strategy_name}")
async def resume_strategy(strategy_name: str):
    """Clear a per-strategy drawdown pause."""
    trading_engine.risk_manager.resume_strategy(strategy_name.upper())
    return {"resumed": True, "strategy": strategy_name.upper()}
