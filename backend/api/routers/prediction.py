"""
ML price prediction endpoints.

POST /api/ml/train          — submit LSTM training job
GET  /api/ml/train/{id}     — poll training status
GET  /api/ml/models         — list trained models (last 20)
POST /api/ml/predict        — run prediction with a trained model
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.logging import get_logger
from tasks.celery_app import celery_app
from tasks.ml_tasks import train_lstm_task

logger = get_logger(__name__)
router = APIRouter(prefix="/api/ml", tags=["ml-prediction"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class TrainRequest(BaseModel):
    symbol: str = Field("BTCUSDT", examples=["BTCUSDT"])
    interval: str = Field("1h", examples=["1h", "4h", "1d"])
    start_date: str = Field(..., examples=["2024-01-01"])
    end_date: str = Field(..., examples=["2024-12-31"])
    seq_len: int = Field(60, ge=20, le=200)
    epochs: int = Field(100, ge=10, le=500)
    hidden_size: int = Field(64, ge=16, le=256)
    num_layers: int = Field(2, ge=1, le=4)


class PredictRequest(BaseModel):
    task_id: str
    horizon: int = Field(24, ge=1, le=168)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/train")
async def submit_training(req: TrainRequest):
    try:
        start = datetime.fromisoformat(req.start_date).replace(tzinfo=timezone.utc)
        end = datetime.fromisoformat(req.end_date).replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise HTTPException(400, f"Invalid date: {exc}")

    if start >= end:
        raise HTTPException(400, "start_date must be before end_date")

    task = train_lstm_task.delay(
        symbol=req.symbol,
        interval=req.interval,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        seq_len=req.seq_len,
        epochs=req.epochs,
        hidden_size=req.hidden_size,
        num_layers=req.num_layers,
    )

    logger.info("LSTM training submitted", extra={"task_id": task.id, "symbol": req.symbol})
    return {
        "task_id": task.id,
        "status": "pending",
        "message": f"Training queued: LSTM on {req.symbol} {req.interval}",
    }


@router.get("/train/{task_id}")
async def get_training_status(task_id: str):
    task = celery_app.AsyncResult(task_id)

    if task.state in ("PENDING", "STARTED"):
        db = await _db_model_row(task_id)
        return db or {"task_id": task_id, "status": "running"}

    if task.state == "FAILURE":
        return {"task_id": task_id, "status": "failed", "error": str(task.result)}

    if task.state == "SUCCESS":
        return {"task_id": task_id, "status": "completed", **task.result}

    return await _db_model_row(task_id) or {"task_id": task_id, "status": task.state.lower()}


@router.get("/models")
async def list_models():
    from db.session import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            text("""
                SELECT task_id, symbol, interval, start_date, end_date,
                       seq_len, hidden_size, num_layers,
                       epochs_trained, n_train_samples, val_loss,
                       status, created_at
                FROM ml_models
                ORDER BY created_at DESC
                LIMIT 20
            """)
        )
        return {"models": [dict(r._mapping) for r in rows]}


@router.post("/predict")
async def predict(req: PredictRequest):
    """
    Load a trained model from DB and run forward prediction.
    Returns `horizon` future price points + 95% confidence band.
    """
    from db.session import AsyncSessionLocal
    from sqlalchemy import text
    from services.ml.lstm_model import predict_future, INTERVAL_MS

    async with AsyncSessionLocal() as session:
        row = await session.execute(
            text("""
                SELECT symbol, interval, seq_len, hidden_size, num_layers,
                       model_data, scaler_data, status
                FROM ml_models
                WHERE task_id = :id
            """),
            {"id": req.task_id},
        )
        r = row.fetchone()

    if r is None:
        raise HTTPException(404, "Model not found")
    m = dict(r._mapping)
    if m["status"] != "completed":
        raise HTTPException(400, f"Model is not ready (status: {m['status']})")
    if not m["model_data"] or not m["scaler_data"]:
        raise HTTPException(500, "Model data missing in DB")

    # Fetch recent OHLCV to seed the prediction
    from tasks.backtest_tasks import _fetch_ohlcv_sync
    from datetime import timedelta

    interval_ms = INTERVAL_MS.get(m["interval"], 3_600_000)
    # We need at least seq_len candles — fetch the most recent ones
    seed_bars = m["seq_len"] + 10
    end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    start_ms = end_ms - seed_bars * interval_ms * 2  # 2× buffer

    ohlcv = _fetch_ohlcv_sync(m["symbol"], m["interval"], start_ms, end_ms)
    if len(ohlcv) < m["seq_len"]:
        raise HTTPException(500, f"Not enough recent data (got {len(ohlcv)} bars)")

    scaler_dict = json.loads(m["scaler_data"])

    predictions = predict_future(
        model_b64=m["model_data"],
        scaler_dict=scaler_dict,
        seed_ohlcv=ohlcv,
        seq_len=m["seq_len"],
        hidden_size=m["hidden_size"],
        num_layers=m["num_layers"],
        horizon=req.horizon,
        n_mc=30,
        interval_ms=interval_ms,
    )

    return {
        "task_id": req.task_id,
        "symbol": m["symbol"],
        "interval": m["interval"],
        "horizon": req.horizon,
        "seed_candles": len(ohlcv),
        "predictions": [
            {
                "step": p.step,
                "timestamp_ms": p.timestamp_ms,
                "price": p.price,
                "price_low": p.price_low,
                "price_high": p.price_high,
            }
            for p in predictions
        ],
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _db_model_row(task_id: str) -> dict | None:
    from db.session import AsyncSessionLocal
    from sqlalchemy import text

    try:
        async with AsyncSessionLocal() as session:
            row = await session.execute(
                text("""
                    SELECT task_id, status, val_loss, epochs_trained,
                           n_train_samples, symbol, interval
                    FROM ml_models WHERE task_id = :id
                """),
                {"id": task_id},
            )
            r = row.fetchone()
            return dict(r._mapping) if r else None
    except Exception:
        return None
