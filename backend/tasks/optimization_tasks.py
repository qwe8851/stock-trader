"""
Celery task for strategy parameter optimization.

Reuses _fetch_ohlcv_sync from backtest_tasks to avoid duplication.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from celery import shared_task
from sqlalchemy import create_engine, text

from core.config import settings
from core.logging import get_logger
from services.optimization.optimizer import run_optimization
from tasks.backtest_tasks import _fetch_ohlcv_sync

logger = get_logger(__name__)


def _save_optimization_sync(task_id: str, data: dict) -> None:
    sync_url = settings.DATABASE_URL.replace("+asyncpg", "")
    engine = create_engine(sync_url)
    try:
        with engine.connect() as conn:
            conn.execute(
                text("""
                    INSERT INTO optimization_results (
                        task_id, strategy, symbol, interval,
                        start_date, end_date, n_trials, objective_metric,
                        best_params, best_value,
                        best_return_pct, best_sharpe, best_drawdown_pct,
                        best_win_rate_pct, best_trades,
                        trials_summary, status, created_at
                    ) VALUES (
                        :task_id, :strategy, :symbol, :interval,
                        :start_date, :end_date, :n_trials, :objective_metric,
                        :best_params, :best_value,
                        :best_return_pct, :best_sharpe, :best_drawdown_pct,
                        :best_win_rate_pct, :best_trades,
                        :trials_summary, 'completed', :created_at
                    )
                    ON CONFLICT (task_id) DO UPDATE SET
                        status = 'completed',
                        best_params = EXCLUDED.best_params,
                        best_value = EXCLUDED.best_value,
                        best_return_pct = EXCLUDED.best_return_pct,
                        best_sharpe = EXCLUDED.best_sharpe,
                        best_drawdown_pct = EXCLUDED.best_drawdown_pct,
                        best_win_rate_pct = EXCLUDED.best_win_rate_pct,
                        best_trades = EXCLUDED.best_trades,
                        trials_summary = EXCLUDED.trials_summary
                """),
                {**data, "created_at": datetime.now(timezone.utc).isoformat()},
            )
            conn.commit()
    finally:
        engine.dispose()


@shared_task(bind=True, name="tasks.run_optimization", max_retries=1)
def run_optimization_task(
    self,
    strategy_name: str,
    symbol: str,
    interval: str,
    start_date: str,
    end_date: str,
    n_trials: int = 50,
    objective_metric: str = "sharpe",
    initial_capital: float = 10_000.0,
) -> dict:
    """
    Fetch OHLCV → run Optuna optimization → save result → return best params.
    """
    task_id = self.request.id
    logger.info("Optimization task started", extra={
        "task_id": task_id, "strategy": strategy_name,
        "symbol": symbol, "n_trials": n_trials,
    })

    # Pre-insert a "running" row so the frontend can detect the job immediately
    sync_url = settings.DATABASE_URL.replace("+asyncpg", "")
    engine = create_engine(sync_url)
    try:
        with engine.connect() as conn:
            conn.execute(
                text("""
                    INSERT INTO optimization_results
                        (task_id, strategy, symbol, interval,
                         start_date, end_date, n_trials, objective_metric, status, created_at)
                    VALUES
                        (:task_id, :strategy, :symbol, :interval,
                         :start_date, :end_date, :n_trials, :objective_metric, 'running', :created_at)
                    ON CONFLICT (task_id) DO NOTHING
                """),
                {
                    "task_id": task_id, "strategy": strategy_name,
                    "symbol": symbol, "interval": interval,
                    "start_date": start_date, "end_date": end_date,
                    "n_trials": n_trials, "objective_metric": objective_metric,
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
        if not ohlcv:
            raise ValueError(f"No OHLCV data for {symbol} {interval}")

        logger.info("OHLCV fetched for optimization", extra={"bars": len(ohlcv)})

        result = run_optimization(
            strategy_name=strategy_name,
            symbol=symbol,
            ohlcv=ohlcv,
            n_trials=n_trials,
            objective_metric=objective_metric,
            interval=interval,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
        )

        trials_json = json.dumps([
            {
                "trial": t.trial_number,
                "params": t.params,
                "sharpe": t.sharpe,
                "return_pct": t.return_pct,
                "drawdown_pct": t.drawdown_pct,
                "win_rate_pct": t.win_rate_pct,
                "total_trades": t.total_trades,
                "value": t.value,
            }
            for t in result.top_trials
        ])

        payload: dict = {
            "task_id": task_id,
            "strategy": result.strategy,
            "symbol": result.symbol,
            "interval": result.interval,
            "start_date": result.start_date,
            "end_date": result.end_date,
            "n_trials": result.n_trials,
            "objective_metric": result.objective_metric,
            "best_params": json.dumps(result.best_params),
            "best_value": result.best_value,
            "best_return_pct": result.best_return_pct,
            "best_sharpe": result.best_sharpe,
            "best_drawdown_pct": result.best_drawdown_pct,
            "best_win_rate_pct": result.best_win_rate_pct,
            "best_trades": result.best_trades,
            "trials_summary": trials_json,
        }

        _save_optimization_sync(task_id, payload)

        logger.info("Optimization task completed", extra={
            "task_id": task_id,
            "best_value": result.best_value,
            "best_params": result.best_params,
        })

        return {**payload, "status": "completed"}

    except Exception as exc:
        logger.error("Optimization task failed", extra={"task_id": task_id, "error": str(exc)})
        engine2 = create_engine(sync_url)
        try:
            with engine2.connect() as conn:
                conn.execute(
                    text("UPDATE optimization_results SET status = 'failed' WHERE task_id = :id"),
                    {"id": task_id},
                )
                conn.commit()
        finally:
            engine2.dispose()
        raise self.retry(exc=exc, countdown=5)
