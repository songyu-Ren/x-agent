# ADR 0004: Authentication and Authorization

## Status
Accepted

## Context
The system exposes privileged operations (view drafts, edit drafts, approve/skip, publish). It must protect these operations while keeping deployment and operations simple for a single-tenant admin workflow.

## Decision
- Use username/password login for an admin user.
- Store sessions server-side in the database with expiration.
- Enforce admin-only access on all UI and action endpoints.
- Use CSRF protections on state-changing requests.

## Consequences
- Operators must configure `ADMIN_USERNAME` and `ADMIN_PASSWORD` in production.
- No external identity provider is required.
- Auditing can attribute actions to a user_id for all protected endpoints.
