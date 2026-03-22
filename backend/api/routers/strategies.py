"""
Strategy management endpoints.

GET  /api/strategies          — list active strategies + engine status
POST /api/strategies          — add a strategy
DELETE /api/strategies/{name} — remove a strategy
POST /api/strategies/resume   — resume after risk halt
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from engine.trading_engine import STRATEGY_REGISTRY, engine

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


class AddStrategyRequest(BaseModel):
    name: str
    symbol: str = "BTCUSDT"
    config: dict = {}


@router.get("")
async def list_strategies():
    return {
        "strategies": engine.list_strategies(),
        "available": list(STRATEGY_REGISTRY.keys()),
        "status": engine.get_status(),
    }


@router.post("")
async def add_strategy(req: AddStrategyRequest):
    try:
        strategy = engine.add_strategy(req.name, req.symbol, req.config)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "message": f"Strategy {strategy.name} added for {req.symbol}",
        "strategy": {
            "name": strategy.name,
            "symbol": req.symbol,
            "config": strategy.config,
        },
    }


@router.delete("/{name}")
async def remove_strategy(name: str, symbol: str = "BTCUSDT"):
    removed = engine.remove_strategy(name, symbol)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found for {symbol}")
    return {"message": f"Strategy {name} removed for {symbol}"}


@router.post("/resume")
async def resume_trading():
    engine.risk_manager.resume()
    return {"message": "Trading resumed"}
