"""
Celery application factory.

Broker  : Redis  (same instance used for pub/sub)
Backend : Redis  (stores task state and results)
"""
from celery import Celery
from celery.schedules import crontab

from core.config import settings

celery_app = Celery(
    "stock_trader",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["tasks.backtest_tasks", "tasks.sentiment_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    result_expires=86400,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Periodic tasks (Celery beat)
    beat_schedule={
        "refresh-sentiment-every-15-minutes": {
            "task": "tasks.refresh_all_sentiment",
            "schedule": crontab(minute="*/15"),
        },
    },
)
