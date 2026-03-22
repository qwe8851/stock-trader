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
    include=["tasks.backtest_tasks", "tasks.sentiment_tasks", "tasks.analytics_tasks", "tasks.optimization_tasks"],
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
        # Sentiment refresh: 매 15분
        "refresh-sentiment-every-15-minutes": {
            "task": "tasks.refresh_all_sentiment",
            "schedule": crontab(minute="*/15"),
        },
        # Portfolio snapshot: 매 1시간
        "save-portfolio-snapshot-hourly": {
            "task": "tasks.save_portfolio_snapshot",
            "schedule": crontab(minute="0"),   # 매시 정각
        },
        # 일일 요약: 매일 09:00 KST (= 00:00 UTC)
        "send-daily-summary": {
            "task": "tasks.send_daily_summary",
            "schedule": crontab(hour="0", minute="0"),
        },
    },
)
