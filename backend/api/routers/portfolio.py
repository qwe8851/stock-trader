"""
Portfolio endpoints.

GET /api/portfolio — full portfolio snapshot (value, holdings, P&L)
"""
from fastapi import APIRouter

from engine.trading_engine import engine

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("")
async def get_portfolio():
    status = engine.get_status()
    portfolio = status["portfolio"]

    initial = 10000.0  # from settings default
    total = portfolio["total_value_usd"]
    pnl_usd = round(total - initial, 2)
    pnl_pct = round((pnl_usd / initial) * 100, 2) if initial else 0.0

    return {
        "total_value_usd": total,
        "available_usd": portfolio["available_usd"],
        "holdings": portfolio["holdings"],
        "open_positions": portfolio["open_positions"],
        "pnl_usd": pnl_usd,
        "pnl_pct": pnl_pct,
        "paper_mode": status["paper_mode"],
        "risk_halted": status["risk_halted"],
    }
