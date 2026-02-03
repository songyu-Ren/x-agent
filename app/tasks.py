from __future__ import annotations

from app.celery_app import celery_app
from app.orchestrator import orchestrator


@celery_app.task(
    name="app.tasks.run_daily",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def run_daily(run_id: str | None = None, source: str = "scheduler") -> str:
    return orchestrator.start_run(source=source, run_id=run_id)


@celery_app.task(
    name="app.tasks.update_style_profile",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def update_style_profile() -> None:
    orchestrator.update_style_profile()


@celery_app.task(
    name="app.tasks.generate_weekly_report",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def generate_weekly_report() -> dict:
    report = orchestrator.generate_weekly_report()
    return report.model_dump(mode="json")
