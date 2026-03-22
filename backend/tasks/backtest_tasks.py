"""
Celery tasks for backtesting.

The task fetches historical OHLCV from Binance, runs the backtest,
and stores the result in PostgreSQL via a synchronous DB session.
"""
import asyncio
import json
from datetime import datetime, timezone

from celery import shared_task
from sqlalchemy import text

from core.config import settings
from core.logging import get_logger
from services.backtesting.runner import run_backtest

logger = get_logger(__name__)


def _fetch_ohlcv_sync(symbol: str, interval: str, start_ms: int, end_ms: int) -> list[dict]:
    """
    Fetch historical klines from Binance synchronously (Celery workers are sync).
    Uses the python-binance Client (not AsyncClient).
    """
    from binance import Client
    client = Client(
        api_key=settings.BINANCE_API_KEY or "",
        api_secret=settings.BINANCE_SECRET_KEY or "",
    )
    raw = client.get_historical_klines(
        symbol=symbol.upper(),
        interval=interval,
        start_str=start_ms,
        end_str=end_ms,
        limit=1000,
    )
    return [
        {
            "time": k[0],
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
        }
        for k in raw
    ]


def _save_result_sync(task_id: str, result_data: dict) -> None:
    """Persist backtest result to PostgreSQL using a synchronous connection."""
    from sqlalchemy import create_engine
    # Convert asyncpg URL to psycopg2-compatible URL for sync access
    sync_url = settings.DATABASE_URL.replace("+asyncpg", "")
    try:
        from sqlalchemy import create_engine as ce
        engine = ce(sync_url)
        with engine.connect() as conn:
            conn.execute(
                text("""
                    INSERT INTO backtest_results
                        (task_id, strategy, symbol, interval, start_date, end_date,
                         initial_capital, final_capital, total_return_pct,
                         sharpe_ratio, max_drawdown_pct, win_rate_pct,
                         total_trades, winning_trades, losing_trades,
                         equity_curve, trades, status, created_at)
                    VALUES
                        (:task_id, :strategy, :symbol, :interval, :start_date, :end_date,
                         :initial_capital, :final_capital, :total_return_pct,
                         :sharpe_ratio, :max_drawdown_pct, :win_rate_pct,
                         :total_trades, :winning_trades, :losing_trades,
                         :equity_curve, :trades, 'completed', :created_at)
                    ON CONFLICT (task_id) DO UPDATE SET
                        status = 'completed',
                        final_capital = EXCLUDED.final_capital,
                        total_return_pct = EXCLUDED.total_return_pct,
                        sharpe_ratio = EXCLUDED.sharpe_ratio,
                        max_drawdown_pct = EXCLUDED.max_drawdown_pct,
                        win_rate_pct = EXCLUDED.win_rate_pct,
                        total_trades = EXCLUDED.total_trades,
                        winning_trades = EXCLUDED.winning_trades,
                        losing_trades = EXCLUDED.losing_trades,
                        equity_curve = EXCLUDED.equity_curve,
                        trades = EXCLUDED.trades
                """),
                {
                    **result_data,
                    "equity_curve": json.dumps(result_data["equity_curve"]),
                    "trades": json.dumps(result_data["trades"]),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            conn.commit()
        engine.dispose()
    except Exception as exc:
        logger.error("Failed to save backtest result", extra={"error": str(exc)})
        raise


@shared_task(bind=True, name="tasks.run_backtest", max_retries=2)
def run_backtest_task(
    self,
    strategy_name: str,
    symbol: str,
    interval: str,
    start_date: str,
    end_date: str,
    config: dict | None = None,
    initial_capital: float = 10_000.0,
) -> dict:
    """
    Celery task: fetch OHLCV → run backtest → save result.

    Returns the result dict (also accessible via Celery result backend).
    """
    task_id = self.request.id
    logger.info("Backtest task started", extra={
        "task_id": task_id, "strategy": strategy_name,
        "symbol": symbol, "interval": interval,
    })

    try:
        # Convert date strings to Unix ms timestamps
        start_ms = int(datetime.fromisoformat(start_date).timestamp() * 1000)
        end_ms = int(datetime.fromisoformat(end_date).timestamp() * 1000)

        # 1. Fetch historical data
        ohlcv = _fetch_ohlcv_sync(symbol, interval, start_ms, end_ms)
        if not ohlcv:
            raise ValueError(f"No OHLCV data returned for {symbol} {interval}")

        logger.info("OHLCV fetched", extra={"bars": len(ohlcv)})

        # 2. Run strategy simulation
        result = run_backtest(
            strategy_name=strategy_name,
            symbol=symbol,
            ohlcv=ohlcv,
            config=config,
            initial_capital=initial_capital,
            interval=interval,
            start_date=start_date,
            end_date=end_date,
        )

        result_data = {
            "task_id": task_id,
            "strategy": result.strategy,
            "symbol": result.symbol,
            "interval": result.interval,
            "start_date": result.start_date,
            "end_date": result.end_date,
            "initial_capital": result.initial_capital,
            "final_capital": result.final_capital,
            "total_return_pct": result.total_return_pct,
            "sharpe_ratio": result.sharpe_ratio,
            "max_drawdown_pct": result.max_drawdown_pct,
            "win_rate_pct": result.win_rate_pct,
            "total_trades": result.total_trades,
            "winning_trades": result.winning_trades,
            "losing_trades": result.losing_trades,
            "equity_curve": result.equity_curve,
            "trades": result.trades,
        }

        # 3. Persist to DB
        _save_result_sync(task_id, result_data)

        logger.info("Backtest task completed", extra={
            "task_id": task_id,
            "return_pct": result.total_return_pct,
            "trades": result.total_trades,
        })
        return result_data

    except Exception as exc:
        logger.error("Backtest task failed", extra={"task_id": task_id, "error": str(exc)})
        # Mark as failed in DB if table exists
        try:
            from sqlalchemy import create_engine
            sync_url = settings.DATABASE_URL.replace("+asyncpg", "")
            engine = create_engine(sync_url)
            with engine.connect() as conn:
                conn.execute(
                    text("""
                        INSERT INTO backtest_results (task_id, strategy, symbol, status, created_at)
                        VALUES (:task_id, :strategy, :symbol, 'failed', :created_at)
                        ON CONFLICT (task_id) DO UPDATE SET status = 'failed'
                    """),
                    {
                        "task_id": task_id,
                        "strategy": strategy_name,
                        "symbol": symbol,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
                conn.commit()
            engine.dispose()
        except Exception:
            pass
        raise self.retry(exc=exc, countdown=5)
