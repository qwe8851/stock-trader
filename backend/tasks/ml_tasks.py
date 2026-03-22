"""
Celery task for LSTM model training.

Flow:
  1. Fetch OHLCV (reuses backtest_tasks._fetch_ohlcv_sync)
  2. Train LSTM via services.ml.lstm_model.train_model()
  3. Store model weights + scaler in ml_models table
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from celery import shared_task
from sqlalchemy import create_engine, text

from core.config import settings
from core.logging import get_logger
from services.ml.lstm_model import train_model, INTERVAL_MS
from tasks.backtest_tasks import _fetch_ohlcv_sync

logger = get_logger(__name__)


def _save_model_sync(task_id: str, data: dict) -> None:
    sync_url = settings.DATABASE_URL.replace("+asyncpg", "")
    engine = create_engine(sync_url)
    try:
        with engine.connect() as conn:
            conn.execute(
                text("""
                    UPDATE ml_models
                    SET status          = 'completed',
                        epochs_trained  = :epochs_trained,
                        n_train_samples = :n_train_samples,
                        val_loss        = :val_loss,
                        model_data      = :model_data,
                        scaler_data     = :scaler_data
                    WHERE task_id = :task_id
                """),
                data,
            )
            conn.commit()
    finally:
        engine.dispose()


@shared_task(bind=True, name="tasks.train_lstm", max_retries=1)
def train_lstm_task(
    self,
    symbol: str,
    interval: str,
    start_date: str,
    end_date: str,
    seq_len: int = 60,
    epochs: int = 100,
    hidden_size: int = 64,
    num_layers: int = 2,
) -> dict:
    """
    Fetch OHLCV → train LSTM → save to DB.
    """
    task_id = self.request.id
    logger.info("LSTM training started", extra={
        "task_id": task_id, "symbol": symbol, "interval": interval,
        "seq_len": seq_len, "epochs": epochs,
    })

    # Pre-insert "running" row
    sync_url = settings.DATABASE_URL.replace("+asyncpg", "")
    engine = create_engine(sync_url)
    try:
        with engine.connect() as conn:
            conn.execute(
                text("""
                    INSERT INTO ml_models
                        (task_id, symbol, interval, start_date, end_date,
                         seq_len, hidden_size, num_layers, status, created_at)
                    VALUES
                        (:task_id, :symbol, :interval, :start_date, :end_date,
                         :seq_len, :hidden_size, :num_layers, 'running', :created_at)
                    ON CONFLICT (task_id) DO NOTHING
                """),
                {
                    "task_id": task_id,
                    "symbol": symbol,
                    "interval": interval,
                    "start_date": start_date,
                    "end_date": end_date,
                    "seq_len": seq_len,
                    "hidden_size": hidden_size,
                    "num_layers": num_layers,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            conn.commit()
    finally:
        engine.dispose()

    try:
        start_ms = int(datetime.fromisoformat(start_date).timestamp() * 1000)
        end_ms = int(datetime.fromisoformat(end_date).timestamp() * 1000)

        ohlcv = _fetch_ohlcv_sync(symbol, interval, start_ms, end_ms)
        if len(ohlcv) < seq_len + 20:
            raise ValueError(
                f"Insufficient data: got {len(ohlcv)} bars, need at least {seq_len + 20}"
            )

        logger.info("OHLCV fetched for LSTM training", extra={"bars": len(ohlcv)})

        result = train_model(
            ohlcv=ohlcv,
            seq_len=seq_len,
            epochs=epochs,
            hidden_size=hidden_size,
            num_layers=num_layers,
        )

        _save_model_sync(task_id, {
            "task_id": task_id,
            "epochs_trained": result.epochs_trained,
            "n_train_samples": result.n_train_samples,
            "val_loss": result.val_loss,
            "model_data": result.model_b64,
            "scaler_data": json.dumps(result.scaler),
        })

        logger.info("LSTM training completed", extra={
            "task_id": task_id,
            "val_loss": result.val_loss,
            "epochs": result.epochs_trained,
        })

        return {
            "task_id": task_id,
            "status": "completed",
            "val_loss": result.val_loss,
            "epochs_trained": result.epochs_trained,
            "n_train_samples": result.n_train_samples,
        }

    except Exception as exc:
        logger.error("LSTM training failed", extra={"task_id": task_id, "error": str(exc)})
        engine2 = create_engine(sync_url)
        try:
            with engine2.connect() as conn:
                conn.execute(
                    text("UPDATE ml_models SET status = 'failed' WHERE task_id = :id"),
                    {"id": task_id},
                )
                conn.commit()
        finally:
            engine2.dispose()
        raise self.retry(exc=exc, countdown=5)
