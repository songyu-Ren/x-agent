# Daily X Agent Design Document

## 1. System Overview
Daily X Agent is an automated system that generates, reviews, and schedules daily tweets based on developer activity (Git logs) and notes (Devlog). It emphasizes a "build-in-public" style and includes a human-in-the-loop approval workflow.

## 2. Architecture

### 2.1 Modules
- **Collector**: Gathers raw materials from Git commits (last 24h) and `devlog.md`.
- **LLM Creator**: Uses OpenRouter (OpenAI compatible) to generate 3 draft options.
- **Reviewer**: Applies heuristics (length, similarity, sensitive words) to select the best draft and flag issues.
- **Storage**: SQLite database to persist drafts, status, and history.
- **Notifier**: Sends Email/WhatsApp with Approve/Edit/Skip links.
- **Web Interface**: FastAPI endpoints for human interaction.
- **Publisher**: Posts to X (Twitter) API.

### 2.2 Data Model (SQLite)
Table: `drafts`
- `token`: UUID (Primary Key)
- `created_at`: Timestamp
- `expires_at`: Timestamp
- `status`: `pending`, `posted`, `skipped`, `error`, `needs_human_attention`, `dry_run_posted`
- `materials_json`: JSON
- `candidates_json`: JSON
- `final_text`: Text
- `tweet_id`: Text (Nullable)
- `last_error`: Text (Nullable)
- `source`: Text (`scheduler` or `manual`)

## 3. Workflow
1.  **Schedule**: Triggers daily at configured time.
2.  **Collect**: Fetch git logs and devlog tail.
3.  **Generate**: LLM produces 3 candidates.
4.  **Review**:
    -   Check length <= 280.
    -   Check similarity vs last 14 days.
    -   Check sensitive words.
    -   If fail, auto-retry once. If fail again, mark `needs_human_attention`.
5.  **Notify**: Send email with links.
6.  **Action**:
    -   **Approve**: Validate token -> Check status -> Re-run Review (safety) -> Post to X -> Update DB.
    -   **Edit**: Show HTML form -> Update DB -> Re-run Review -> Show status.
    -   **Skip**: Update DB.

## 4. API Endpoints
- `GET /health`: Health check.
- `GET /approve/{token}`: Trigger publish.
- `GET /edit/{token}`: Show edit form.
- `POST /edit/{token}`: Save changes.
- `GET /skip/{token}`: Mark as skipped.
- `POST /generate-now`: Manual trigger.
- `GET /drafts`: List recent drafts.

## 5. Security
- **Token**: UUIDs for one-time/limited-time links.
- **Basic Auth**: Optional protection for web endpoints.
- **Sensitive Data**: Environment variables for keys; logs sanitized.
