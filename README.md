# Daily X Agent

A fully automated Daily X (Twitter) Agent that collects your development progress (git logs, devlog), generates draft tweets using LLM, and sends them to you for approval via Email/WhatsApp before posting.

## Features
- **Daily Collection**: Scans git commits and `devlog.md`.
- **AI Generation**: Creates 3 candidates in "build-in-public" style.
- **Safety Gates**: Checks length, sensitive words, and duplicates (Jaccard similarity).
- **Human-in-the-loop**: Email notifications with "Approve", "Edit", "Skip" links.
- **Web Interface**: Mobile-friendly pages for review and editing.
- **Dry Run**: Test the whole flow without actually posting to X.

## Quick Start (Local)

1. **Clone & Setup**
   ```bash
   git clone <repo>
   cd daily-x-agent
   pip install -r requirements.txt
   ```

2. **Configuration**
   Copy example config:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and fill in your keys (OpenRouter, Twitter, SendGrid/SMTP).
   *Note: For local testing, you can use MailHog (see Docker section) or just set DRY_RUN=true.*

3. **Run Server**
   ```bash
   uvicorn app.main:app --reload
   ```
   Open http://localhost:8000/health to verify.

4. **Verify / Smoke Test**
   To trigger a cycle immediately (instead of waiting for the scheduler):
   ```bash
   # If you set Basic Auth, include -u user:pass
   curl -X POST http://localhost:8000/generate-now -u admin:secret
   ```
   Check your email (or MailHog http://localhost:8025) for the draft notification.

## Docker Deployment (Recommended)

Includes **MailHog** for capturing emails locally so you don't need a real SMTP server for testing.

1. **Build & Run**
   ```bash
   docker-compose up --build -d
   ```

2. **Access**
   - Agent: http://localhost:8000
   - MailHog: http://localhost:8025 (View sent emails here)

## Public Exposure (For Mobile Access)

To approve tweets from your phone, the `BASE_PUBLIC_URL` in `.env` must be accessible from the internet.

### Option 1: Cloudflare Tunnel (Recommended)
1. Install `cloudflared`.
2. Run: `cloudflared tunnel --url http://localhost:8000`
3. Copy the generated URL (e.g., `https://funny-name.trycloudflare.com`) to `BASE_PUBLIC_URL` in `.env`.
4. Restart the agent.

### Option 2: VPS + Nginx
Deploy the Docker container on a VPS and set up Nginx as a reverse proxy with Let's Encrypt SSL.

## Development

- **Run Tests**:
  ```bash
  pytest tests/
  ```

- **Project Structure**:
  - `app/`: Source code.
  - `app/collector.py`: Git/File data gathering.
  - `app/llm.py`: OpenRouter interaction.
  - `app/reviewer.py`: Quality gates.
  - `app/web.py`: FastAPI endpoints.

## Verification Steps (For Delivery)

1. **Dry Run Mode**:
   - Ensure `DRY_RUN=true` in `.env`.
   - Trigger generation: `curl -X POST http://localhost:8000/generate-now -u admin:secret`.
   - Open MailHog (http://localhost:8025), find the email.
   - Click "Approve" link.
   - You should see a success page saying "Tweet posted successfully! ID: ... (Fake)".
   - The real X API was NOT called.

2. **Live Mode**:
   - Set `DRY_RUN=false` and provide valid Twitter Credentials.
   - Repeat steps. The tweet will appear on your profile.
