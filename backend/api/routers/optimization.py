"""
Strategy parameter optimization endpoints.

POST /api/optimize        — submit an optimization job
GET  /api/optimize/{id}   — poll status + result
GET  /api/optimize        — list recent results
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.logging import get_logger
from tasks.celery_app import celery_app
from tasks.optimization_tasks import run_optimization_task

logger = get_logger(__name__)
router = APIRouter(prefix="/api/optimize", tags=["optimization"])


class OptimizeRequest(BaseModel):
    strategy: str = Field(..., examples=["RSI", "MACD"])
    symbol: str = Field("BTCUSDT", examples=["BTCUSDT"])
    interval: str = Field("1h", examples=["1h", "4h", "1d"])
    start_date: str = Field(..., examples=["2024-01-01"])
    end_date: str = Field(..., examples=["2024-12-31"])
    n_trials: int = Field(50, ge=10, le=300)
    objective_metric: str = Field("sharpe", examples=["sharpe", "return", "calmar"])
    initial_capital: float = Field(10_000.0, gt=0)


@router.post("")
async def submit_optimization(req: OptimizeRequest):
    try:
        start = datetime.fromisoformat(req.start_date).replace(tzinfo=timezone.utc)
        end = datetime.fromisoformat(req.end_date).replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise HTTPException(400, f"Invalid date: {exc}")

    if start >= end:
        raise HTTPException(400, "start_date must be before end_date")

    if req.strategy.upper() not in ("RSI", "MACD"):
        raise HTTPException(400, "strategy must be RSI or MACD")

    if req.objective_metric not in ("sharpe", "return", "calmar"):
        raise HTTPException(400, "objective_metric must be sharpe, return, or calmar")

    task = run_optimization_task.delay(
        strategy_name=req.strategy,
        symbol=req.symbol,
        interval=req.interval,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        n_trials=req.n_trials,
        objective_metric=req.objective_metric,
        initial_capital=req.initial_capital,
    )

    logger.info("Optimization submitted", extra={
        "task_id": task.id, "strategy": req.strategy,
        "n_trials": req.n_trials,
    })

    return {
        "task_id": task.id,
        "status": "pending",
        "message": f"Optimization queued: {req.strategy} on {req.symbol} ({req.n_trials} trials)",
    }


@router.get("/{task_id}")
async def get_optimization_result(task_id: str):
    task = celery_app.AsyncResult(task_id)

    if task.state == "PENDING":
        # Also check DB — task may have been pre-inserted as "running"
        return await _db_status(task_id) or {"task_id": task_id, "status": "pending"}

    if task.state == "STARTED":
        return await _db_status(task_id) or {"task_id": task_id, "status": "running"}

    if task.state == "FAILURE":
        return {"task_id": task_id, "status": "failed", "error": str(task.result)}

    if task.state == "SUCCESS":
        result = task.result
        return {"task_id": task_id, "status": "completed", "result": _parse_result(result)}

    return await _db_status(task_id) or {"task_id": task_id, "status": task.state.lower()}


@router.get("")
async def list_optimizations():
    from db.session import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            text("""
                SELECT task_id, strategy, symbol, interval, start_date, end_date,
                       n_trials, objective_metric, best_value, best_return_pct,
                       best_sharpe, best_drawdown_pct, best_win_rate_pct, best_trades,
                       best_params, status, created_at
                FROM optimization_results
                ORDER BY created_at DESC
                LIMIT 20
            """)
        )
        results = []
        for row in rows:
            r = dict(row._mapping)
            if r.get("best_params"):
                try:
                    r["best_params"] = json.loads(r["best_params"])
                except Exception:
                    pass
            results.append(r)

    return {"results": results}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _db_status(task_id: str) -> dict | None:
    """Look up task status from DB (used while Celery is still running)."""
    from db.session import AsyncSessionLocal
    from sqlalchemy import text

    try:
        async with AsyncSessionLocal() as session:
            row = await session.execute(
                text("SELECT status, best_params, best_value, best_return_pct, "
                     "best_sharpe, best_drawdown_pct, best_win_rate_pct, best_trades, "
                     "trials_summary, strategy, symbol, n_trials, objective_metric "
                     "FROM optimization_results WHERE task_id = :id"),
                {"id": task_id},
            )
            r = row.fetchone()
            if r is None:
                return None
            d = dict(r._mapping)
            if d["status"] == "completed":
                return {"task_id": task_id, "status": "completed", "result": _parse_db_row(d)}
            return {"task_id": task_id, "status": d["status"]}
    except Exception:
        return None


def _parse_result(r: dict) -> dict:
    """Deserialise JSON blobs from Celery result."""
    out = dict(r)
    for key in ("best_params", "trials_summary"):
        if isinstance(out.get(key), str):
            try:
                out[key] = json.loads(out[key])
            except Exception:
                pass
    return out


def _parse_db_row(r: dict) -> dict:
    out = dict(r)
    for key in ("best_params", "trials_summary"):
        if isinstance(out.get(key), str):
            try:
                out[key] = json.loads(out[key])
            except Exception:
                pass
    return out
