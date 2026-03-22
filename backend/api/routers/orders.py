"""
Order endpoints.

GET /api/orders          — recent orders (paper + live)
GET /api/orders/holdings — current holdings
"""
from fastapi import APIRouter, Query

from engine.trading_engine import engine

router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.get("")
async def get_orders(limit: int = Query(50, ge=1, le=200)):
    orders = engine.order_manager.get_orders(limit=limit)
    return {"orders": orders, "total": len(orders)}


@router.get("/holdings")
async def get_holdings():
    return {
        "holdings": engine.order_manager.get_holdings(),
        "available_usd": engine.order_manager.available_usd,
    }
