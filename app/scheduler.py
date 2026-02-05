import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.orchestrator import orchestrator
from app.runtime_config import get_int, get_str

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


async def scheduled_job():
    logger.info("Scheduler triggering daily run...")
    orchestrator.start_run(source="scheduler")


async def scheduled_style_update():
    logger.info("Scheduler triggering weekly style update...")
    orchestrator.update_style_profile()


async def scheduled_weekly_report():
    logger.info("Scheduler triggering weekly report...")
    orchestrator.generate_weekly_report()


def start_scheduler():
    hour = get_int("schedule_hour", settings.SCHEDULE_HOUR)
    minute = get_int("schedule_minute", settings.SCHEDULE_MINUTE)
    timezone = get_str("timezone", settings.TIMEZONE)
    trigger = CronTrigger(hour=hour, minute=minute, timezone=timezone)
    scheduler.add_job(scheduled_job, trigger)

    style_weekday = int(getattr(settings, "STYLE_UPDATE_WEEKDAY", 1) or 1)
    style_hour = int(getattr(settings, "STYLE_UPDATE_HOUR", 9) or 9)
    scheduler.add_job(
        scheduled_style_update,
        CronTrigger(
            day_of_week=(style_weekday - 1) % 7,
            hour=style_hour,
            minute=0,
            timezone=timezone,
        ),
    )

    report_weekday = int(getattr(settings, "WEEKLY_REPORT_WEEKDAY", 1) or 1)
    report_hour = int(getattr(settings, "WEEKLY_REPORT_HOUR", 10) or 10)
    scheduler.add_job(
        scheduled_weekly_report,
        CronTrigger(
            day_of_week=(report_weekday - 1) % 7,
            hour=report_hour,
            minute=0,
            timezone=timezone,
        ),
    )
    scheduler.start()
    logger.info(f"Scheduler started. Next run at {hour}:{minute} {timezone}")
