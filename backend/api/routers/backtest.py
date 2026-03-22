"""
Backtest endpoints.

POST /api/backtest          — submit a new backtest job
GET  /api/backtest/{task_id} — poll status + result
GET  /api/backtest           — list recent results
"""
import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.logging import get_logger
from tasks.celery_app import celery_app
from tasks.backtest_tasks import run_backtest_task

logger = get_logger(__name__)
router = APIRouter(prefix="/api/backtest", tags=["backtest"])


class BacktestRequest(BaseModel):
    strategy: str = Field(..., examples=["RSI"])
    symbol: str = Field("BTCUSDT", examples=["BTCUSDT"])
    interval: str = Field("1h", examples=["1h", "4h", "1d"])
    start_date: str = Field(..., examples=["2024-01-01"])
    end_date: str = Field(..., examples=["2024-12-31"])
    initial_capital: float = Field(10_000.0, gt=0)
    config: dict = Field(default_factory=dict)


@router.post("")
async def submit_backtest(req: BacktestRequest):
    """
    Enqueue a backtest job.
    Returns the task_id for polling.
    """
    # Validate dates
    try:
        start = datetime.fromisoformat(req.start_date).replace(tzinfo=timezone.utc)
        end = datetime.fromisoformat(req.end_date).replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {exc}")

    if start >= end:
        raise HTTPException(status_code=400, detail="start_date must be before end_date")

    task = run_backtest_task.delay(
        strategy_name=req.strategy,
        symbol=req.symbol,
        interval=req.interval,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        config=req.config,
        initial_capital=req.initial_capital,
    )

    logger.info("Backtest submitted", extra={
        "task_id": task.id, "strategy": req.strategy, "symbol": req.symbol,
    })

    return {
        "task_id": task.id,
        "status": "pending",
        "message": f"Backtest queued for {req.strategy} on {req.symbol}",
    }


@router.get("/{task_id}")
async def get_backtest_result(task_id: str):
    """
    Poll the status of a backtest task.

    States: PENDING → STARTED → SUCCESS / FAILURE
    When SUCCESS, the full result is returned.
    """
    task = celery_app.AsyncResult(task_id)

    if task.state == "PENDING":
        return {"task_id": task_id, "status": "pending"}

    if task.state == "STARTED":
        return {"task_id": task_id, "status": "running"}

    if task.state == "FAILURE":
        return {
            "task_id": task_id,
            "status": "failed",
            "error": str(task.result),
        }

    if task.state == "SUCCESS":
        result = task.result
        # Deserialise JSON blobs if they came back as strings
        if isinstance(result.get("equity_curve"), str):
            result["equity_curve"] = json.loads(result["equity_curve"])
        if isinstance(result.get("trades"), str):
            result["trades"] = json.loads(result["trades"])
        return {"task_id": task_id, "status": "completed", "result": result}

    return {"task_id": task_id, "status": task.state.lower()}


@router.get("")
async def list_backtests():
    """
    Return the last 20 backtest results from PostgreSQL.
    """
    from db.session import async_session_factory
    from sqlalchemy import text

    async with async_session_factory() as session:
        rows = await session.execute(
            text("""
                SELECT task_id, status, strategy, symbol, interval,
                       start_date, end_date, initial_capital, final_capital,
                       total_return_pct, sharpe_ratio, max_drawdown_pct,
                       win_rate_pct, total_trades, created_at
                FROM backtest_results
                ORDER BY created_at DESC
                LIMIT 20
            """)
        )
        results = [dict(row._mapping) for row in rows]

    return {"results": results}
