"""
Portfolio endpoints.

GET  /api/portfolio               — full portfolio snapshot (value, holdings, P&L)
GET  /api/portfolio/allocation    — current target allocation from DB
POST /api/portfolio/allocation    — set target allocation
GET  /api/portfolio/weights       — current real-time weights
GET  /api/portfolio/rebalance     — preview rebalance trades
POST /api/portfolio/rebalance     — execute rebalance trades (paper)
GET  /api/portfolio/correlation   — asset correlation matrix
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.binance import BinanceAdapter
from db.session import get_db
from engine.strategies.base import Signal, SignalAction
from engine.trading_engine import engine
from services.portfolio.allocation import compute_current_weights, compute_rebalance
from services.portfolio.correlation import compute_correlation_matrix

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

_SUPPORTED_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _load_allocations(db: AsyncSession) -> dict[str, float]:
    """Return {symbol: target_pct} from DB."""
    rows = await db.execute(sa.text("SELECT symbol, target_pct FROM portfolio_allocations"))
    return {row.symbol: row.target_pct for row in rows.fetchall()}


async def _fetch_prices(symbols: list[str]) -> dict[str, float]:
    """Get latest prices — prefer in-memory engine prices, fall back to REST."""
    prices: dict[str, float] = {}
    missing: list[str] = []

    for sym in symbols:
        p = engine._latest_prices.get(sym.upper())
        if p:
            prices[sym.upper()] = p
        else:
            missing.append(sym.upper())

    if missing:
        adapter = BinanceAdapter()
        try:
            for sym in missing:
                candles = await adapter.get_ohlcv(sym, interval="1m", limit=1)
                if candles:
                    prices[sym] = float(candles[-1]["close"])
        except Exception:
            pass
        finally:
            await adapter.close()

    return prices


# ---------------------------------------------------------------------------
# GET /api/portfolio
# ---------------------------------------------------------------------------

@router.get("")
async def get_portfolio():
    status = engine.get_status()
    portfolio = status["portfolio"]

    initial = 10000.0
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


# ---------------------------------------------------------------------------
# GET /api/portfolio/allocation
# ---------------------------------------------------------------------------

@router.get("/allocation")
async def get_allocation(db: AsyncSession = Depends(get_db)):
    """Return current target allocation settings."""
    allocs = await _load_allocations(db)
    total_pct = round(sum(allocs.values()), 2)
    return {
        "targets": [
            {"symbol": sym, "target_pct": pct}
            for sym, pct in sorted(allocs.items())
        ],
        "total_pct": total_pct,
    }


# ---------------------------------------------------------------------------
# POST /api/portfolio/allocation
# ---------------------------------------------------------------------------

class AllocationItem(BaseModel):
    symbol: str
    target_pct: float = Field(..., ge=0, le=100)


class AllocationRequest(BaseModel):
    targets: list[AllocationItem]


@router.post("/allocation")
async def set_allocation(
    req: AllocationRequest,
    db: AsyncSession = Depends(get_db),
):
    """Save target allocation. Replaces all existing targets."""
    total = sum(item.target_pct for item in req.targets)
    if total > 100.01:
        raise HTTPException(400, f"Target percentages sum to {total:.2f}% — must be ≤ 100%")

    now = datetime.now(timezone.utc)

    # Upsert each symbol
    await db.execute(sa.text("DELETE FROM portfolio_allocations"))
    for item in req.targets:
        if item.target_pct <= 0:
            continue
        await db.execute(
            sa.text(
                "INSERT INTO portfolio_allocations (symbol, target_pct, updated_at) "
                "VALUES (:sym, :pct, :ts)"
            ),
            {"sym": item.symbol.upper(), "pct": item.target_pct, "ts": now},
        )

    return {"saved": True, "targets": len(req.targets), "total_pct": round(total, 2)}


# ---------------------------------------------------------------------------
# GET /api/portfolio/weights
# ---------------------------------------------------------------------------

@router.get("/weights")
async def get_weights():
    """Return current real-time allocation weights."""
    holdings = engine.order_manager.get_holdings()
    available = engine.order_manager.available_usd

    symbols = [asset + "USDT" for asset in holdings]
    prices = await _fetch_prices(symbols)

    weights = compute_current_weights(holdings, available, prices)
    return {"weights": weights}


# ---------------------------------------------------------------------------
# GET /api/portfolio/rebalance  (preview)
# ---------------------------------------------------------------------------

@router.get("/rebalance")
async def preview_rebalance(db: AsyncSession = Depends(get_db)):
    """Preview the trades required to reach target allocation."""
    targets = await _load_allocations(db)
    if not targets:
        return {"trades": [], "message": "No allocation targets set"}

    holdings = engine.order_manager.get_holdings()
    available = engine.order_manager.available_usd
    prices = await _fetch_prices(list(targets.keys()))

    trades = compute_rebalance(holdings, available, prices, targets)
    return {
        "trades": [
            {
                "symbol": t.symbol,
                "side": t.side,
                "amount_usd": t.amount_usd,
                "current_pct": t.current_pct,
                "target_pct": t.target_pct,
                "current_value_usd": t.current_value_usd,
                "target_value_usd": t.target_value_usd,
            }
            for t in trades
        ],
    }


# ---------------------------------------------------------------------------
# POST /api/portfolio/rebalance  (execute)
# ---------------------------------------------------------------------------

@router.post("/rebalance")
async def execute_rebalance(db: AsyncSession = Depends(get_db)):
    """Execute rebalance trades (paper mode)."""
    if not engine.order_manager:
        raise HTTPException(503, "Trading engine not ready")

    targets = await _load_allocations(db)
    if not targets:
        raise HTTPException(400, "No allocation targets set")

    holdings = engine.order_manager.get_holdings()
    available = engine.order_manager.available_usd
    prices = await _fetch_prices(list(targets.keys()))

    trades = compute_rebalance(holdings, available, prices, targets)
    if not trades:
        return {"executed": 0, "message": "Portfolio already balanced"}

    executed: list[dict[str, Any]] = []
    for trade in trades:
        price = prices.get(trade.symbol, 0.0)
        if price <= 0:
            continue

        signal = Signal(
            action=SignalAction.BUY if trade.side == "BUY" else SignalAction.SELL,
            symbol=trade.symbol,
            confidence=1.0,
            reason="Portfolio rebalance",
            metadata={"strategy": "REBALANCE"},
        )
        order = await engine.order_manager.execute(
            signal=signal,
            size_usd=trade.amount_usd,
            current_price=price,
        )
        if order:
            executed.append(order)

    return {"executed": len(executed), "orders": executed}


# ---------------------------------------------------------------------------
# GET /api/portfolio/correlation
# ---------------------------------------------------------------------------

@router.get("/correlation")
async def get_correlation(
    symbols: str = "BTCUSDT,ETHUSDT,SOLUSDT",
    interval: str = "1h",
    limit: int = 100,
):
    """
    Compute pairwise correlation of log-returns for the given symbols.

    Query params:
      symbols  — comma-separated list (default: BTCUSDT,ETHUSDT,SOLUSDT)
      interval — candle interval (default: 1h)
      limit    — number of candles to fetch per symbol (default: 100)
    """
    sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if len(sym_list) < 2:
        raise HTTPException(400, "At least 2 symbols are required")

    adapter = BinanceAdapter()
    price_histories: dict[str, list[float]] = {}

    try:
        for sym in sym_list:
            candles = await adapter.get_ohlcv(sym, interval=interval, limit=limit)
            if candles:
                price_histories[sym] = [float(c["close"]) for c in candles]
    finally:
        await adapter.close()

    if len(price_histories) < 2:
        raise HTTPException(502, "Could not fetch price data for correlation analysis")

    matrix = compute_correlation_matrix(price_histories)
    return {
        "symbols": list(matrix.keys()),
        "matrix": matrix,
        "interval": interval,
        "data_points": {sym: len(prices) for sym, prices in price_histories.items()},
    }
