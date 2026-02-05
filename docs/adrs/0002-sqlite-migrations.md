# ADR 0002: Idempotent SQLite Migrations

## Status
Accepted

## Context
The system persists state in SQLite and must support safe upgrades across versions without manual steps.

## Decision
- Use an internal migration runner that records applied migrations in a `schema_migrations` table.
- Each migration is idempotent:
  - `CREATE TABLE IF NOT EXISTS`
  - `ALTER TABLE ADD COLUMN` only when missing

## Consequences
- The application can auto-upgrade on startup.
- Operators can deploy new versions without coordinating schema changes separately.
- The migration runner must remain backward compatible and well-tested.
