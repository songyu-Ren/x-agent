# Daily X Agent (Multi-Agent Architecture)

An automated Twitter agent powered by a multi-agent system to collect, curate, write, critique, and publish daily engineering updates.

## Architecture

This system uses 7 specialized agents orchestrated by a central state machine:

1.  **CollectorAgent**: Gathers git logs and devlogs.
2.  **CuratorAgent**: Decides the daily topic angle.
3.  **WriterAgent**: Drafts content (build-in-public style).
4.  **CriticAgent**: Reviews and refines the draft.
5.  **PolicyAgent**: Checks safety, length, and fact-grounding.
6.  **NotifierAgent**: Emails the human for approval.
7.  **PublisherAgent**: Posts to X after approval.

See `docs/design.md` for full architectural details.

## Setup & Run

### 1. Environment
Copy `.env.example` to `.env` and fill in keys:
```bash
cp .env.example .env
```
Required: `OPENROUTER_API_KEY`, `TWITTER_API_KEY` (and related), `SENDGRID_API_KEY` (or SMTP).

### 2. Local Run
```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
- Web UI: http://localhost:8000
- Health Check: http://localhost:8000/health

### 3. Docker (Recommended)
Includes MailHog for local email testing.

```bash
docker-compose up --build -d
```
- Agent: http://localhost:8000
- MailHog: http://localhost:8025 (View sent emails here)

## How to Verify (Smoke Test)

1.  **Start System**: Run via Docker Compose.
2.  **Trigger Run**: 
    ```bash
    curl -X POST http://localhost:8000/generate-now -u admin:secret
    ```
    *(Assuming default basic auth)*
3.  **Check Email**: Open MailHog (http://localhost:8025). You should see a "Daily X Draft" email.
4.  **Review**: The email contains the draft and a Policy Report.
5.  **Approve (Dry Run)**:
    - Ensure `DRY_RUN=true` in `.env`.
    - Click "Approve" link in email (or copy link to browser).
    - You should see "Success" and a fake tweet ID.
6.  **Verify DB**:
    - The draft status should be `dry_run_posted`.

## Public Exposure
To approve from your phone, expose port 8000 via **Cloudflare Tunnel**:
```bash
cloudflared tunnel --url http://localhost:8000
```
Copy the resulting URL to `BASE_PUBLIC_URL` in `.env` and restart.

## Development
- **Tests**: `pytest tests/`
- **DB**: SQLite (`daily_agent.db`)
