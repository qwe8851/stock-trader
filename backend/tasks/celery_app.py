"""
Celery application factory.

Broker  : Redis  (same instance used for pub/sub)
Backend : Redis  (stores task state and results)
"""
from celery import Celery

from core.config import settings

celery_app = Celery(
    "stock_trader",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["tasks.backtest_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Keep results for 24 hours
    result_expires=86400,
    # Retry failed tasks up to 3 times with exponential back-off
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)
