from __future__ import annotations

from fastapi import FastAPI


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

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.instrumentation.requests import RequestsInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource, sampler=TraceIdRatioBased(sample_ratio))
    trace.set_tracer_provider(provider)

    if otlp_endpoint:
        headers_dict = {}
        if otlp_headers:
            parts = [p.strip() for p in otlp_headers.split(",") if p.strip()]
            for p in parts:
                if "=" in p:
                    k, v = p.split("=", 1)
                    headers_dict[k.strip()] = v.strip()
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint, headers=headers_dict or None)
        provider.add_span_processor(BatchSpanProcessor(exporter))

    FastAPIInstrumentor.instrument_app(app)
    RequestsInstrumentor().instrument()
    HTTPXClientInstrumentor().instrument()
