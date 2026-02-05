from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import cast

from fastapi import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response as StarletteResponse

RUNS_TOTAL = Counter(
    "runs_total",
    "Total orchestrator runs started",
    labelnames=("source",),
)
RUNS_FAILED_TOTAL = Counter(
    "runs_failed_total",
    "Total orchestrator runs failed",
    labelnames=("source",),
)
JOB_LATENCY_SECONDS = Histogram(
    "job_latency_seconds",
    "Job latency in seconds",
    labelnames=("job",),
    buckets=(0.25, 0.5, 1, 2, 5, 10, 30, 60, 120, 300, 600),
)
NOTIFY_TOTAL = Counter(
    "notify_total",
    "Notifications attempted",
    labelnames=("channel", "status"),
)
PUBLISH_TOTAL = Counter(
    "publish_total",
    "Publish attempts",
    labelnames=("status", "dry_run"),
)
POLICY_FAIL_TOTAL = Counter(
    "policy_fail_total",
    "Policy failures (non-PASS outcomes)",
    labelnames=("action",),
)
AGENT_LATENCY_SECONDS = Histogram(
    "agent_latency_seconds",
    "Agent execution latency in seconds",
    labelnames=("agent",),
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60),
)

HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests",
    labelnames=("method", "path", "status"),
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    labelnames=("method", "path"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
)

DB_RUNS_TOTAL = Gauge("dailyx_runs_total", "Runs total", labelnames=("status",))
DB_DRAFTS_TOTAL = Gauge("dailyx_drafts_total", "Drafts total")
DB_POSTS_TOTAL = Gauge("dailyx_posts_total", "Posts total")
DB_AVG_RUN_DURATION_MS = Gauge("dailyx_run_duration_avg_ms", "Average run duration ms")


def _route_path(request: Request) -> str:
    route = request.scope.get("route")
    path = cast(str | None, getattr(route, "path", None))
    if path and isinstance(path, str):
        return path
    return request.url.path


class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[StarletteResponse]]
    ) -> StarletteResponse:
        start = time.perf_counter()
        path = _route_path(request)
        method = request.method
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration = time.perf_counter() - start
            HTTP_REQUESTS_TOTAL.labels(method=method, path=path, status=str(status_code)).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(method=method, path=path).observe(duration)


def _update_db_gauges() -> None:
    from app.config import settings

    if str(getattr(settings, "METRICS_INCLUDE_DB", "true")).lower() != "true":
        return

    from infrastructure.db.repositories import (
        avg_run_duration_ms,
        drafts_count,
        posts_count,
        runs_grouped_by_status,
    )
    from infrastructure.db.session import get_sessionmaker

    with get_sessionmaker()() as session:
        for status, count in runs_grouped_by_status(session):
            DB_RUNS_TOTAL.labels(status=status).set(count)
        DB_DRAFTS_TOTAL.set(drafts_count(session))
        DB_POSTS_TOTAL.set(posts_count(session))
        DB_AVG_RUN_DURATION_MS.set(avg_run_duration_ms(session))


def metrics_endpoint_response() -> Response:
    _update_db_gauges()
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
