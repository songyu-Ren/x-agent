import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import settings
from app.database import init_db
from app.observability.logging import setup_logging
from app.observability.metrics import PrometheusMiddleware, metrics_endpoint_response
from app.observability.otel import setup_otel
from app.web import router

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
        if not settings.BASIC_AUTH_USER or not settings.BASIC_AUTH_PASS:
            raise RuntimeError("BASIC_AUTH_USER and BASIC_AUTH_PASS must be set in production")
    init_db()
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


@app.middleware("http")
async def secure_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Cross-Origin-Resource-Policy", "same-site")
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
