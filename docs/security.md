# Security (v3)

## Threat Model
Primary risks:
- Unauthorized publishing (approving or posting without the owner).
- Secret leakage (API keys appearing in logs, drafts, or UI).
- Public exposure of internal draft content or approval endpoints.

## Controls
### Authentication
- Admin-only UI protected by username/password login with server-side sessions.
- In `ENV=production`, the server fails fast unless `ADMIN_USERNAME` and `ADMIN_PASSWORD` are set (bootstraps an admin user on startup).
- Sessions are stored in the database with expiration (`SESSION_TTL_HOURS`).
- Session cookies are `HttpOnly` with `SameSite=Lax`; `Secure` is enabled in production.

### Approval Tokens
- Draft approval uses time-limited tokens stored in the database.
- Tokens are consumed after approval/skip to prevent replay.
- Tokens are stored as hashes; raw tokens are never persisted.

### CSRF
- Login sets a short-lived CSRF cookie and validates a form token.
- State-changing actions validate a session-bound CSRF token.

### Secrets Hygiene
- JSON logging is used and avoids printing raw materials by default.
- Operators must provide secrets via environment variables.
- In `ENV=production`, the server fails fast if `SECRET_KEY` is not set to a non-default value.
- Correlation IDs (`request_id`, `run_id`, `draft_id`, `user_id`) are included to support debugging without logging secrets.
- Logs should redact sensitive values; never log raw API keys, cookies, or authorization headers.

### Content Safety
- Blocked terms list is enforced before publishing.
- Fact-grounding checks reject unsupported claims when evidence is missing.
- Safe defaults: approval required and `DRY_RUN=true` until explicitly disabled.

### Network Hardening
- Trusted host allowlist can be enforced via `ALLOWED_HOSTS`.
- Optional CORS allowlist via `CORS_ORIGINS`.
- Security headers are added to all responses.
- Rate limits are applied to login and action endpoints.
  - Multiple workers are safe; run a single scheduler to avoid duplicate enqueues.

### Error Reporting
- Optional Sentry reporting can be enabled via `SENTRY_ENABLED=true` and `SENTRY_DSN`.

## Operational Recommendations
- Run behind HTTPS (reverse proxy or managed ingress).
- Restrict inbound access to the web UI (VPN/Zero Trust) if possible.
- Rotate OpenRouter/X/Twilio credentials regularly.
