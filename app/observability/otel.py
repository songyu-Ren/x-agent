from __future__ import annotations

from fastapi import FastAPI

_otel_initialized = False


def _parse_headers(raw: str) -> dict[str, str]:
    headers_dict: dict[str, str] = {}
    parts = [p.strip() for p in (raw or "").split(",") if p.strip()]
    for p in parts:
        if "=" in p:
            k, v = p.split("=", 1)
            headers_dict[k.strip()] = v.strip()
    return headers_dict


def _init_tracing(
    *,
    service_name: str,
    otlp_endpoint: str | None,
    otlp_headers: str,
    sample_ratio: float,
) -> None:
    global _otel_initialized
    if _otel_initialized:
        return

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource, sampler=TraceIdRatioBased(sample_ratio))
    trace.set_tracer_provider(provider)

    if otlp_endpoint:
        headers_dict = _parse_headers(otlp_headers)
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint, headers=headers_dict or None)
        provider.add_span_processor(BatchSpanProcessor(exporter))

    _otel_initialized = True


def setup_otel(
    *,
    app: FastAPI,
    enabled: bool,
    service_name: str,
    otlp_endpoint: str | None,
    otlp_headers: str,
    sample_ratio: float,
) -> None:
    if not enabled:
        return

    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.instrumentation.requests import RequestsInstrumentor

    _init_tracing(
        service_name=service_name,
        otlp_endpoint=otlp_endpoint,
        otlp_headers=otlp_headers,
        sample_ratio=sample_ratio,
    )

    FastAPIInstrumentor.instrument_app(app)
    RequestsInstrumentor().instrument()
    HTTPXClientInstrumentor().instrument()


def setup_otel_worker(
    *,
    enabled: bool,
    service_name: str,
    otlp_endpoint: str | None,
    otlp_headers: str,
    sample_ratio: float,
) -> None:
    if not enabled:
        return

    _init_tracing(
        service_name=service_name,
        otlp_endpoint=otlp_endpoint,
        otlp_headers=otlp_headers,
        sample_ratio=sample_ratio,
    )
