# ADR 0005: Database Choice

## Status
Accepted

## Context
The application persists runs, drafts, posts, audit logs, and idempotency records. It needs a durable store with simple deployment for single-tenant usage, while keeping an upgrade path for larger deployments.

## Decision
- Default to SQLite for local development and single-instance deployments.
- Support configuring an alternative database URL (e.g., Postgres) via environment configuration.
- Keep schema upgrades automated via idempotent migrations.

## Consequences
- SQLite enables a low-friction deployment model and easy backup (single file).
- Operators can move to a managed database when concurrency or durability requirements grow.
