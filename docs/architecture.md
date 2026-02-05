# Architecture (v3)

## Overview
Daily X Agent is a production-oriented content automation system for generating, reviewing, and publishing daily X/Twitter posts from real developer materials. It is designed around a multi-agent pipeline with a central orchestrator and a mandatory human approval step.

Primary properties:
- Human-in-the-loop is mandatory before publishing.
- Every run is persisted for auditability.
- External calls are retried and failures are observable.

## Core Flow
1. A run is triggered by the scheduler or manual endpoint.
2. The orchestrator executes agents in order:
   - Collector → Curator → Style → ThreadPlanner → Writer → Critic → Policy → Notifier
3. Human reviews via web UI and either:
   - Approves (optionally after edits) → Re-Policy → Publisher
   - Skips → Draft is marked skipped

## Components
```mermaid
flowchart LR
  subgraph Runtime
    U[Admin User] -->|HTTP| UI[Approval Console (Next.js)]
    UI -->|HTTP JSON| API[FastAPI app.web]
    API -->|enqueue| Q[Celery + Redis]
    S[APScheduler] -->|trigger| ORCH[Orchestrator]
    Q -->|run tasks| ORCH
    ORCH --> A1[Collector]
    ORCH --> A2[Curator]
    ORCH --> A3[Style]
    ORCH --> A4[ThreadPlanner]
    ORCH --> A5[Writer]
    ORCH --> A6[Critic]
    ORCH --> A7[Policy]
    ORCH --> A8[Notifier]
    API -->|approve/edit/skip| ORCH
    ORCH --> PUB[Publisher]
    ORCH --> DB[(SQLAlchemy DB)]
    API --> DB
  end
```

## Deployable Units
- `api`: FastAPI app serving REST APIs, metrics, and (optional) legacy HTML UI.
- `worker`: Celery worker executing orchestrator runs.
- `scheduler`: single scheduler (Celery beat) enqueueing periodic jobs.
- `frontend`: Next.js Approval Console calling the API over JSON.
- `db`: Postgres in production (SQLite acceptable for single-tenant dev).
- `redis`: Celery broker/backend.

### FastAPI App
- Entry point: `app.main:app`
- Web UI + APIs: `app.web`
- Background workflow: `app.orchestrator`
- Scheduler: `app.scheduler`

### Database
- SQLite by default.
- Schema is upgraded via Alembic migrations.
- Tables persist runs, drafts, posts, style profiles, weekly reports, and thread posts.

#### Data Model (high level)
- `runs`: one per workflow execution (status, duration, last_error).
- `drafts`: one per run output (final text or thread tweets, policy report, status).
- `agent_logs`: one per agent per run (timings, summaries, model_used, errors/warnings).
- `action_tokens`: time-limited tokens for approve/skip/edit flows (hashed token storage).
- `publish_attempts`: publish locking/idempotency for retry-safe publishing.
- `posts`: published tweets/thread positions (idempotent insert by draft/position).
- `auth_users`, `auth_sessions`, `audit_logs`: admin login/session + audit trail for actions.
- `app_config`: runtime config (schedule, blocked terms, feature flags).

### Agents
- Agents are isolated modules with structured input/output.
- Agents never call other agents directly.
- All agent execution is scheduled by the orchestrator.

### Integrations
- LLM: OpenRouter (OpenAI-compatible `chat.completions`)
- X posting: Tweepy v2 `create_tweet`
- Notifications: SMTP/SendGrid email, optional Twilio WhatsApp

## API Surface (v3)
- Auth: `/api/auth/csrf`, `/api/auth/login`, `/api/auth/logout`, `/api/auth/me`
- Draft review/actions: `/api/drafts`, `/api/drafts/{id}`, `/api/drafts/{id}/edit`, `/api/drafts/{id}/approve`, `/api/drafts/{id}/skip`, `/api/drafts/{id}/regenerate`, `/api/drafts/{id}/resume`
- Runs: `/api/runs`
- System: `/api/health`, `/api/metrics`

## Draft State Machine
```mermaid
stateDiagram-v2
  [*] --> needs_human_attention: policy!=PASS
  [*] --> pending: policy=PASS
  pending --> publishing: approve
  pending --> skipped: skip
  needs_human_attention --> pending: edit+recheck(policy=PASS)
  needs_human_attention --> skipped: skip
  publishing --> posted: publish success
  publishing --> dry_run_posted: publish success (dry_run)
  publishing --> error: publish failure
  pending --> expired: token TTL elapsed
  needs_human_attention --> expired: token TTL elapsed
  expired --> [*]

## Observability
### Logging
- Structured JSON logs by default.
- Trace context is included when OpenTelemetry tracing is enabled.
- Correlation IDs are included when present: `request_id`, `run_id`, `draft_id`, `user_id`.

### Metrics
- Prometheus exposition endpoint exposes:
  - HTTP request counters and latency histograms
  - Optional DB-derived gauges (runs/drafts/posts)
- Workflow metrics include: `runs_total`, `runs_failed_total`, `job_latency_seconds`, `notify_total`, `publish_total`, `policy_fail_total`, `agent_latency_seconds`.

### Tracing
- Minimal viable OpenTelemetry tracing with:
  - FastAPI instrumentation
  - Requests + HTTPX instrumentation
  - Optional OTLP exporter via env config

## Reasonable Assumptions
- SQLite is acceptable for single-tenant and small-scale usage; the migration system provides forward compatibility.
- The legacy HTML UI remains available; the preferred UI is the Next.js Approval Console.
