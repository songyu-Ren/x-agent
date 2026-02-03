from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.config import settings

broker_url = settings.CELERY_BROKER_URL or settings.REDIS_URL
result_backend = settings.CELERY_RESULT_BACKEND or settings.REDIS_URL

celery_app = Celery(
    "daily_x_agent", broker=broker_url, backend=result_backend, include=["app.tasks"]
)
celery_app.conf.timezone = settings.TIMEZONE
celery_app.conf.enable_utc = True

celery_app.conf.task_acks_late = True
celery_app.conf.task_reject_on_worker_lost = True
celery_app.conf.worker_prefetch_multiplier = 1

style_weekday = int(getattr(settings, "STYLE_UPDATE_WEEKDAY", 1) or 1)
style_hour = int(getattr(settings, "STYLE_UPDATE_HOUR", 9) or 9)
report_weekday = int(getattr(settings, "WEEKLY_REPORT_WEEKDAY", 1) or 1)
report_hour = int(getattr(settings, "WEEKLY_REPORT_HOUR", 10) or 10)

celery_app.conf.beat_schedule = {
    "daily-run": {
        "task": "app.tasks.run_daily",
        "schedule": crontab(hour=settings.SCHEDULE_HOUR, minute=settings.SCHEDULE_MINUTE),
        "kwargs": {"source": "scheduler"},
    },
    "weekly-style-update": {
        "task": "app.tasks.update_style_profile",
        "schedule": crontab(day_of_week=(style_weekday - 1) % 7, hour=style_hour, minute=0),
    },
    "weekly-report": {
        "task": "app.tasks.generate_weekly_report",
        "schedule": crontab(day_of_week=(report_weekday - 1) % 7, hour=report_hour, minute=0),
    },
}
