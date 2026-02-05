# Runbooks (v3)

## Local Development
### Setup
```bash
cp .env.example .env
pip install -r requirements.txt -r requirements-dev.txt
```

### Run (API)
```bash
uvicorn app.main:app --reload --port 8000
```

### Run (Worker)
```bash
celery -A app.celery_app.celery_app worker -l INFO
```

### Validate
```bash
ruff check .
ruff format --check .
black --check .
mypy app tests
python -m pytest -q
python -m coverage run --source=app,domain,infrastructure -m pytest -q
python -m coverage report
```

## Docker Compose
```bash
docker-compose up --build
```

Services:
- App: http://localhost:8000
- MailHog: http://localhost:8025
- Prometheus: http://localhost:9090

## Troubleshooting
### Metrics endpoint not reachable
- Ensure `METRICS_ENABLED=true`.
- If scraping a non-default route, set `METRICS_PATH` and scrape the same path.

### No workflow metrics (runs_total, agent_latency_seconds, etc.)
- Ensure the process exposing `/metrics` is the one executing runs (FastAPI and/or Celery worker).
- If only the worker is running, metrics will be exported from the worker process if it exposes an HTTP server; this project exports metrics from the FastAPI process.

### Approve fails with 410
- Token expired. Trigger a new run and approve within `TOKEN_TTL_HOURS`.

### Login redirects to /login repeatedly
- Ensure `ADMIN_USERNAME` and `ADMIN_PASSWORD` are set at startup (admin bootstrap).
- Verify cookies are not blocked and the host matches `BASE_PUBLIC_URL` for your environment.

### Traces not appearing
- Set `OTEL_ENABLED=true`.
- Provide `OTEL_EXPORTER_OTLP_ENDPOINT` and (if needed) `OTEL_EXPORTER_OTLP_HEADERS`.
- If you only run the worker, ensure it can reach the OTLP endpoint.

### Sentry not reporting
- Set `SENTRY_ENABLED=true` and `SENTRY_DSN=...`.
- Ensure outbound network access to Sentry from the running environment.

## Backup and Restore (SQLite)
- Backup: copy the DB file configured by `DB_PATH`.
- Restore: stop the service, replace the DB file, restart.

## Test Strategy
- Unit tests:
  - Policy claim extraction + evidence grounding behavior (PASS vs REWRITE/HOLD).
  - Approval idempotency and publish locking (no duplicate posts).
  - Token hashing, TTL expiration, and one-time token consumption.
- Integration tests:
  - FastAPI JSON flows with `TestClient`: login, list drafts, draft detail, edit/policy check, approve/skip/regenerate stubs.
  - Celery tasks in eager mode: ensure tasks call orchestrator entrypoints and return expected values.
- Frontend:
  - Keep UI logic thin; rely on Next.js build + ESLint as baseline checks.
