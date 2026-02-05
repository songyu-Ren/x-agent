from __future__ import annotations

import contextlib
import time
import uuid

from celery import current_task

from app.celery_app import celery_app
from app.config import settings
from app.observability.logging import bind_correlation_ids, reset_correlation_ids
from app.observability.metrics import JOB_LATENCY_SECONDS
from app.observability.otel import setup_otel_worker
from app.orchestrator import orchestrator

_sentry_initialized = False


def _setup_sentry() -> None:
    global _sentry_initialized
    if _sentry_initialized:
        return
    if not bool(getattr(settings, "SENTRY_ENABLED", False)):
        return
    dsn = getattr(settings, "SENTRY_DSN", None)
    if not dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.celery import CeleryIntegration

        sentry_sdk.init(
            dsn=str(dsn),
            environment=str(getattr(settings, "ENV", "development")),
            traces_sample_rate=float(getattr(settings, "SENTRY_TRACES_SAMPLE_RATE", 0.0) or 0.0),
            integrations=[CeleryIntegration()],
        )
        _sentry_initialized = True
    except Exception:
        _sentry_initialized = True


@celery_app.task(
    name="app.tasks.run_daily",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def run_daily(
    run_id: str | None = None,
    source: str = "scheduler",
    request_id: str | None = None,
    user_id: str | None = None,
) -> str:
    _setup_sentry()
    setup_otel_worker(
        enabled=bool(getattr(settings, "OTEL_ENABLED", False)),
        service_name=settings.OTEL_SERVICE_NAME,
        otlp_endpoint=getattr(settings, "OTEL_EXPORTER_OTLP_ENDPOINT", None),
        otlp_headers=str(getattr(settings, "OTEL_EXPORTER_OTLP_HEADERS", "") or ""),
        sample_ratio=float(getattr(settings, "OTEL_TRACES_SAMPLER_RATIO", 0.1) or 0.1),
    )
    run_id = run_id or str(uuid.uuid4())
    task_id = str(getattr(getattr(current_task, "request", None), "id", "") or "")
    tokens = bind_correlation_ids(
        request_id=(request_id or task_id or None),
        run_id=run_id,
        user_id=user_id,
    )
    start = time.perf_counter()
    try:
        try:
            from opentelemetry import trace

            tracer = trace.get_tracer(__name__)
            with tracer.start_as_current_span("celery.task.run_daily") as span:
                span.set_attribute("celery.task_id", task_id)
                span.set_attribute("run_id", run_id)
                span.set_attribute("source", source)
                if user_id:
                    span.set_attribute("user_id", str(user_id))
                return orchestrator.start_run(source=source, run_id=run_id)
        except Exception:
            return orchestrator.start_run(source=source, run_id=run_id)
    finally:
        with contextlib.suppress(Exception):
            JOB_LATENCY_SECONDS.labels(job="celery_run_daily").observe(time.perf_counter() - start)
        reset_correlation_ids(tokens)


@celery_app.task(
    name="app.tasks.update_style_profile",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def update_style_profile() -> None:
    _setup_sentry()
    task_id = str(getattr(getattr(current_task, "request", None), "id", "") or "")
    tokens = bind_correlation_ids(request_id=(task_id or None))
    start = time.perf_counter()
    try:
        setup_otel_worker(
            enabled=bool(getattr(settings, "OTEL_ENABLED", False)),
            service_name=settings.OTEL_SERVICE_NAME,
            otlp_endpoint=getattr(settings, "OTEL_EXPORTER_OTLP_ENDPOINT", None),
            otlp_headers=str(getattr(settings, "OTEL_EXPORTER_OTLP_HEADERS", "") or ""),
            sample_ratio=float(getattr(settings, "OTEL_TRACES_SAMPLER_RATIO", 0.1) or 0.1),
        )
        try:
            from opentelemetry import trace

            tracer = trace.get_tracer(__name__)
            with tracer.start_as_current_span("celery.task.update_style_profile") as span:
                span.set_attribute("celery.task_id", task_id)
                orchestrator.update_style_profile()
        except Exception:
            orchestrator.update_style_profile()
    finally:
        with contextlib.suppress(Exception):
            JOB_LATENCY_SECONDS.labels(job="celery_update_style_profile").observe(
                time.perf_counter() - start
            )
        reset_correlation_ids(tokens)


@celery_app.task(
    name="app.tasks.generate_weekly_report",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def generate_weekly_report() -> dict:
    _setup_sentry()
    task_id = str(getattr(getattr(current_task, "request", None), "id", "") or "")
    tokens = bind_correlation_ids(request_id=(task_id or None))
    start = time.perf_counter()
    try:
        setup_otel_worker(
            enabled=bool(getattr(settings, "OTEL_ENABLED", False)),
            service_name=settings.OTEL_SERVICE_NAME,
            otlp_endpoint=getattr(settings, "OTEL_EXPORTER_OTLP_ENDPOINT", None),
            otlp_headers=str(getattr(settings, "OTEL_EXPORTER_OTLP_HEADERS", "") or ""),
            sample_ratio=float(getattr(settings, "OTEL_TRACES_SAMPLER_RATIO", 0.1) or 0.1),
        )
        try:
            from opentelemetry import trace

            tracer = trace.get_tracer(__name__)
            with tracer.start_as_current_span("celery.task.generate_weekly_report") as span:
                span.set_attribute("celery.task_id", task_id)
                report = orchestrator.generate_weekly_report()
                return report.model_dump(mode="json")
        except Exception:
            report = orchestrator.generate_weekly_report()
            return report.model_dump(mode="json")
    finally:
        with contextlib.suppress(Exception):
            JOB_LATENCY_SECONDS.labels(job="celery_generate_weekly_report").observe(
                time.perf_counter() - start
            )
        reset_correlation_ids(tokens)
