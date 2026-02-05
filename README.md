# Daily X Agent

Daily X Agent is a production-minded, human-in-the-loop automation that drafts a daily “building in public” update and (optionally) publishes it to X/Twitter after approval.

It’s designed for:
- Deterministic persistence (SQLAlchemy 2.0 + Alembic migrations)
- Background execution (Redis + Celery worker/beat)
- Basic operational hygiene (metrics, optional OpenTelemetry, CI checks)

## Contents

- [What it does](#what-it-does)
- [How it works](#how-it-works)
- [Quickstart (Docker)](#quickstart-docker)
- [Run locally (Python)](#run-locally-python)
- [Configuration](#configuration)
- [Database & migrations](#database--migrations)
- [Background jobs (Celery)](#background-jobs-celery)
- [API & UI endpoints](#api--ui-endpoints)
- [Development](#development)
- [Troubleshooting](#troubleshooting)
- [Production deployment](#production-deployment)

## What it does

1. Collects material from your sources (git, devlog, and optional Notion/GitHub/RSS).
2. Chooses a topic angle, drafts candidate tweets, then critiques and refines them.
3. Runs policy checks (length, blocked terms, similarity, etc.).
4. Notifies a human (email; optional WhatsApp) with an approval link.
5. Publishes to X/Twitter only after approval (and only if `DRY_RUN=false`).

## How it works

**Agent pipeline**
- `CollectorAgent` gathers evidence/materials.
- `CuratorAgent` picks the day’s topic plan.
- `WriterAgent` produces candidates.
- `CriticAgent` selects and edits the final draft.
- `PolicyAgent` validates safety/quality constraints.
- `NotifierAgent` sends the draft + approval link.
- `PublisherAgent` posts to X/Twitter after approval.

**Architecture boundaries**
- `domain/`: Pydantic models (data contracts).
- `application/`: interfaces/types for application-level flows.
- `infrastructure/`: database (SQLAlchemy models, repositories, Alembic runner).
- `app/`: FastAPI web app + concrete agent implementations + orchestration.

## Quickstart (Docker)

This runs:
- `api` (FastAPI)
- `worker` (Celery worker)
- `scheduler` (Celery beat)
- `postgres` + `redis`
- `mailhog` (local email inbox)
- optional `prometheus` + `otel-collector`

```bash
cp .env.example .env
docker-compose up --build -d
```

Open:
- Web/UI: http://localhost:8000
- MailHog: http://localhost:8025
- Prometheus: http://localhost:9090

### Smoke test

1. Ensure `.env` has `DRY_RUN=true` (default).
2. Trigger a run:

```bash
curl -X POST http://localhost:8000/generate-now -u admin:secret
```

3. Open MailHog and find the draft email.
4. Click the approval link. In dry-run mode, no real tweet is sent.

## Run locally (Python)

Prereqs:
- Python 3.11
- Redis (for Celery) if you use `/generate-now`
- Postgres optional (SQLite is the default if `DATABASE_URL` is unset)

```bash
cp .env.example .env
pip install -r requirements.txt -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
```

If you want `/generate-now` to enqueue tasks locally, you also need:

```bash
celery -A app.celery_app worker -l info
celery -A app.celery_app beat -l info
```

## Configuration

Configuration is loaded from `.env` (see [.env.example](file:///Users/songyuren/Documents/PersonalProject/x-agent/.env.example)).

### Minimum config for a useful local setup

- LLM: `OPENROUTER_API_KEY`
- Email: `EMAIL_PROVIDER=smtp` with MailHog (`SMTP_SERVER=localhost`, `SMTP_PORT=1025`)
- Auth (recommended): `BASIC_AUTH_USER`, `BASIC_AUTH_PASS`

### Posting safety

- `DRY_RUN=true` by default. Keep it enabled until you’re confident.
- To actually post, set `DRY_RUN=false` and provide all Twitter credentials:
  `TWITTER_API_KEY`, `TWITTER_API_SECRET`, `TWITTER_ACCESS_TOKEN`, `TWITTER_ACCESS_TOKEN_SECRET`.

### Production notes

When `ENV=production`, the app refuses to start unless:
- `SECRET_KEY` is set to a non-default value
- `BASIC_AUTH_USER` and `BASIC_AUTH_PASS` are set

## Database & migrations

The application uses SQLAlchemy 2.0 and Alembic.

- Default DB (no `DATABASE_URL`): SQLite file at `DB_PATH` (default: `daily_agent.db`)
- Production DB: Postgres, e.g. `postgresql+psycopg://user:pass@host:5432/db`

In development, migrations are applied on startup. In production, run migrations as a separate step.

To run migrations manually:

```bash
alembic upgrade head
```

## Background jobs (Celery)

Celery is configured in [celery_app.py](file:///Users/songyuren/Documents/PersonalProject/x-agent/app/celery_app.py):
- Broker/backend defaults to `REDIS_URL` unless overridden by `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND`.
- Beat schedules:
  - daily run (`app.tasks.run_daily`)
  - weekly style update (`app.tasks.update_style_profile`)
  - weekly report (`app.tasks.generate_weekly_report`)

The web endpoint `/generate-now` enqueues a Celery task rather than running the pipeline inline.

## API & UI endpoints

- `GET /health` — health check
- `GET /metrics` — Prometheus metrics (can also be served on `METRICS_PATH`)
- `POST /generate-now` — enqueue a run (requires Basic Auth if configured)
- `GET /drafts` — list drafts (requires Basic Auth)
- `GET /draft/{token}` — draft detail (requires Basic Auth)
- `GET /edit/{token}` / `POST /edit/{token}` — edit flow (requires Basic Auth)
- `GET /approve/{token}` — approve + publish (requires Basic Auth)
- `GET /skip/{token}` — skip a draft (requires Basic Auth)

## Development

```bash
pre-commit install
python -m ruff check .
python -m ruff format --check .
black --check .
mypy app tests
python -m pytest -q
```

## Troubleshooting

### `pytest` can’t import `app.*`

Use `python -m pytest` (this matches CI) so the repository root is on `sys.path`:

```bash
python -m pytest -q
```

### No emails show up

- If you use Docker, check MailHog at http://localhost:8025
- Verify `EMAIL_PROVIDER=smtp`, `SMTP_SERVER`, `SMTP_PORT`, and `EMAIL_TO`

### `/generate-now` hangs or errors

That endpoint enqueues a Celery task:
- ensure Redis is reachable via `REDIS_URL`
- ensure a Celery worker is running (`celery -A app.celery_app worker -l info`)

## Production deployment

### Reverse proxy (Caddy example)

```caddyfile
example.com {
  encode gzip
  reverse_proxy 127.0.0.1:8000
}
```

### Reverse proxy (nginx example)

```nginx
server {
  listen 80;
  server_name example.com;

  location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
  }
}
```

### Required env vars (production)

- `ENV=production`
- `SECRET_KEY` (non-default)
- `ADMIN_USERNAME`, `ADMIN_PASSWORD` (admin login for the console/API)
- `DATABASE_URL` (recommended Postgres)
- `REDIS_URL`

To post to X/Twitter (set `DRY_RUN=false`):
- `TWITTER_API_KEY`, `TWITTER_API_SECRET`, `TWITTER_ACCESS_TOKEN`, `TWITTER_ACCESS_TOKEN_SECRET`

### Migrations (production)

Run migrations before starting new app versions:

```bash
alembic upgrade head
```

### Scaling notes

- Run multiple `worker` instances for throughput.
- Run exactly one `scheduler` (Celery beat) instance.
- Run one or more `api` instances behind the reverse proxy.
