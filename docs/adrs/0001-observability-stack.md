# ADR 0001: Observability Stack

## Status
Accepted

## Context
The system needs production-grade observability with:
- Prometheus metrics
- Structured JSON logs
- Minimal viable distributed tracing

## Decision
- Metrics: `prometheus-client` with an HTTP middleware for request metrics and a scrape endpoint.
- Logging: JSON log formatter emitting one JSON object per line, with optional trace context fields.
- Tracing: OpenTelemetry instrumentation for FastAPI + requests/httpx, exporting via OTLP when configured.

## Consequences
- Prometheus scraping becomes a standard way to monitor request rate/latency and DB totals.
- Logs are machine-parseable and consistent across services.
- Tracing can be enabled without code changes in environments that provide an OTLP endpoint.
