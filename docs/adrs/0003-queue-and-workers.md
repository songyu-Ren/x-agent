# ADR 0003: Queue and Worker Model

## Status
Accepted

## Context
The system needs a reliable way to run the daily workflow and periodic jobs without blocking the web server, with retry support and operational visibility.

## Decision
- Use Celery for background jobs.
- Use Redis as the broker (and optional result backend).
- Expose a manual trigger endpoint that enqueues a Celery job.

## Consequences
- Deployments run at least two processes: the FastAPI web server and a Celery worker.
- Redis becomes an operational dependency.
- Workflow execution gains automatic retry primitives and separation from HTTP request latency.
