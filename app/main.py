import logging
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import PlainTextResponse

from app.config import settings
from app.database import init_db
from app.observability.logging import setup_logging
from app.observability.metrics import PrometheusMiddleware, metrics_endpoint_response
from app.observability.otel import setup_otel
from app.web import router
from infrastructure.db import repositories as db
from infrastructure.db.session import get_sessionmaker

setup_logging(
    log_level=settings.LOG_LEVEL,
    log_format=settings.LOG_FORMAT,
    service_name=settings.OTEL_SERVICE_NAME,
)
logger = logging.getLogger(__name__)


def _cors_origins() -> list[str]:
    raw = getattr(settings, "CORS_ORIGINS", "") or ""
    return [o.strip() for o in raw.split(",") if o.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Daily X Agent...")
    if settings.ENV == "production":
        if settings.SECRET_KEY in (
            "unsafe_default_secret",
            "",
            "change_this_to_random_secret_string",
        ):
            raise RuntimeError("SECRET_KEY must be set in production")
        if not settings.ADMIN_USERNAME or not settings.ADMIN_PASSWORD:
            raise RuntimeError("ADMIN_USERNAME and ADMIN_PASSWORD must be set in production")
    init_db()
    if settings.ADMIN_USERNAME and settings.ADMIN_PASSWORD:
        with get_sessionmaker()() as session:
            _ = db.ensure_user(
                session,
                username=settings.ADMIN_USERNAME,
                raw_password=settings.ADMIN_PASSWORD,
                role="admin",
            )
            session.commit()
    yield
    logger.info("Shutting down Daily X Agent...")


app = FastAPI(title="Daily X Agent", lifespan=lifespan)

allowed_hosts = (getattr(settings, "ALLOWED_HOSTS", "*") or "*").strip()
if allowed_hosts != "*":
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=[h.strip() for h in allowed_hosts.split(",") if h.strip()],
    )

origins = _cors_origins()
if origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

if str(getattr(settings, "METRICS_ENABLED", "true")).lower() == "true":
    app.add_middleware(PrometheusMiddleware)
    metrics_path = getattr(settings, "METRICS_PATH", "/metrics") or "/metrics"
    if isinstance(metrics_path, str) and metrics_path.strip() and metrics_path != "/metrics":
        app.add_api_route(metrics_path, metrics_endpoint_response, methods=["GET"])

_rate_limit_windows: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def _rate_limit_key(path: str, method: str) -> str | None:
    if path == "/health" or path == "/metrics":
        return None
    if path == "/login" and method == "POST":
        return "auth"
    if path.startswith(
        (
            "/approve/",
            "/skip/",
            "/edit/",
            "/regenerate/",
            "/edit-id/",
            "/regenerate-id/",
        )
    ):
        return "actions"
    if path == "/generate-now" and method == "POST":
        return "actions"
    return None


def _check_rate_limit(bucket: str, ip: str, limit: int, window_seconds: int = 60) -> bool:
    now = time.monotonic()
    window = _rate_limit_windows[(bucket, ip)]
    while window and now - window[0] > window_seconds:
        window.popleft()
    if len(window) >= limit:
        return False
    window.append(now)
    return True


@app.middleware("http")
async def rate_limit(request, call_next):
    bucket = _rate_limit_key(request.url.path, request.method)
    if bucket:
        ip = getattr(getattr(request, "client", None), "host", None) or "unknown"
        limit = (
            int(getattr(settings, "RATE_LIMIT_AUTH_PER_MIN", 10) or 10)
            if bucket == "auth"
            else int(getattr(settings, "RATE_LIMIT_ACTION_PER_MIN", 60) or 60)
        )
        if not _check_rate_limit(bucket, ip, limit=limit, window_seconds=60):
            return PlainTextResponse("Too Many Requests", status_code=429)
    return await call_next(request)


@app.middleware("http")
async def secure_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Cross-Origin-Resource-Policy", "same-site")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; img-src 'self' data:; base-uri 'self'; frame-ancestors 'none'",
    )
    if settings.ENV == "production":
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    return response


setup_otel(
    app=app,
    enabled=bool(getattr(settings, "OTEL_ENABLED", False)),
    service_name=settings.OTEL_SERVICE_NAME,
    otlp_endpoint=getattr(settings, "OTEL_EXPORTER_OTLP_ENDPOINT", None),
    otlp_headers=str(getattr(settings, "OTEL_EXPORTER_OTLP_HEADERS", "") or ""),
    sample_ratio=float(getattr(settings, "OTEL_TRACES_SAMPLER_RATIO", 0.1) or 0.1),
)

app.include_router(router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
