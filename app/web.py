import json
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Query, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.config import settings
from app.database import get_connection
from app.orchestrator import orchestrator

router = APIRouter()
security = HTTPBasic()


def _require_basic(credentials: HTTPBasicCredentials = Depends(security)):
    if not settings.BASIC_AUTH_USER or not settings.BASIC_AUTH_PASS:
        return "anonymous"

    ok_user = secrets.compare_digest(
        credentials.username.encode("utf8"), settings.BASIC_AUTH_USER.encode("utf8")
    )
    ok_pass = secrets.compare_digest(
        credentials.password.encode("utf8"), settings.BASIC_AUTH_PASS.encode("utf8")
    )
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def _auth_dep():
    if settings.BASIC_AUTH_USER and settings.BASIC_AUTH_PASS:
        return Depends(_require_basic)
    return lambda: None


def _html(title: str, body: str, status_code: int = 200) -> HTMLResponse:
    page = f"""
<!doctype html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title} - Daily X Agent</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; padding: 16px; max-width: 760px; margin: 0 auto; }}
    pre {{ white-space: pre-wrap; background: #f7f7f7; padding: 12px; border-radius: 8px; border: 1px solid #eee; }}
    .btn {{ display: inline-block; padding: 10px 14px; border-radius: 8px; text-decoration: none; color: white; margin-right: 8px; }}
    .green {{ background: #1f8b4c; }}
    .blue {{ background: #1a73e8; }}
    .gray {{ background: #6b7280; }}
    .red {{ background: #b42318; }}
    .muted {{ color: #666; }}
    textarea {{ width: 100%; min-height: 120px; font-size: 16px; padding: 10px; border-radius: 8px; border: 1px solid #ddd; }}
    .row {{ margin: 10px 0; }}
    .card {{ border: 1px solid #eee; border-radius: 10px; padding: 12px; margin: 12px 0; }}
    code {{ background: #f0f0f0; padding: 2px 6px; border-radius: 6px; }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  {body}
</body>
</html>
"""
    return HTMLResponse(page, status_code=status_code)


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/metrics")
def metrics():
    if str(getattr(settings, "METRICS_ENABLED", "true")).lower() != "true":
        return JSONResponse({"enabled": False}, status_code=404)
    conn = get_connection()
    runs_total = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    runs_failed = conn.execute("SELECT COUNT(*) FROM runs WHERE status='failed'").fetchone()[0]
    avg_latency = conn.execute(
        "SELECT AVG(duration_ms) FROM runs WHERE duration_ms IS NOT NULL"
    ).fetchone()[0]
    drafts_total = conn.execute("SELECT COUNT(*) FROM drafts").fetchone()[0]
    posts_total = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    conn.close()
    return {
        "runs_total": runs_total,
        "runs_failed_total": runs_failed,
        "avg_generation_latency_ms": int(avg_latency or 0),
        "notifications_sent_total": drafts_total,
        "posts_published_total": posts_total,
    }


@router.post("/generate-now", dependencies=[_auth_dep()])
async def generate_now(background_tasks: BackgroundTasks):
    background_tasks.add_task(orchestrator.start_run, source="manual")
    return {"message": "run triggered"}


@router.get("/approve/{token}", response_class=HTMLResponse, dependencies=[_auth_dep()])
def approve(token: str):
    code, msg = orchestrator.approve_draft(token)
    if code == 200:
        return _html("Approve", f"<div class='card'><p>{msg}</p></div>")
    if code == 410:
        return _html("Expired", "<p class='red'>Token expired (410)</p>", status_code=410)
    return _html("Approve Failed", f"<p class='red'>{msg}</p>", status_code=code)


@router.get("/skip/{token}", response_class=HTMLResponse, dependencies=[_auth_dep()])
def skip(token: str):
    code, msg = orchestrator.skip_draft(token)
    return _html("Skip", f"<p>{msg}</p>", status_code=code)


@router.get("/drafts", response_class=HTMLResponse, dependencies=[_auth_dep()])
def list_drafts(status_filter: str | None = Query(default=None, alias="status")):
    conn = get_connection()
    since = datetime.now(timezone.utc) - timedelta(days=14)
    if status_filter:
        rows = conn.execute(
            """
            SELECT token, created_at, status, final_text FROM drafts
            WHERE created_at >= ? AND status = ?
            ORDER BY created_at DESC
            LIMIT 200
            """,
            (since, status_filter),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT token, created_at, status, final_text FROM drafts
            WHERE created_at >= ?
            ORDER BY created_at DESC
            LIMIT 200
            """,
            (since,),
        ).fetchall()
    conn.close()
    items = []
    for r in rows:
        token = r[0]
        created_at = str(r[1])[:16]
        st = r[2]
        preview = (r[3] or "")[:80]
        items.append(
            f"<li><code>{created_at}</code> <b>{st}</b> — {preview} <a href='/draft/{token}'>details</a> <a href='/edit/{token}'>edit</a></li>"
        )
    filt = (
        "<div class='row muted'>Filter: "
        "<a href='/drafts'>all</a> | "
        "<a href='/drafts?status=pending'>pending</a> | "
        "<a href='/drafts?status=posted'>posted</a> | "
        "<a href='/drafts?status=skipped'>skipped</a> | "
        "<a href='/drafts?status=needs_human_attention'>needs_attention</a>"
        "</div>"
    )
    body = filt + "<ul>" + "".join(items) + "</ul>"
    return _html("Drafts (14 days)", body)


@router.get("/draft/{token}", response_class=HTMLResponse, dependencies=[_auth_dep()])
def draft_detail(token: str):
    conn = get_connection()
    d = conn.execute("SELECT * FROM drafts WHERE token=?", (token,)).fetchone()
    if not d:
        conn.close()
        return _html("Not Found", "<p>draft not found</p>", status_code=404)
    run = None
    if d["run_id"]:
        run = conn.execute("SELECT * FROM runs WHERE run_id=?", (d["run_id"],)).fetchone()
    conn.close()

    def _pre(title: str, value: str | None):
        return f"<div class='card'><h3>{title}</h3><pre>{value or ''}</pre></div>"

    body = (
        f"<div class='card'><p><b>Status:</b> {d['status']}</p>"
        f"<p><b>Token:</b> <code>{d['token']}</code></p>"
        f"<p><a class='btn green' href='/approve/{token}'>Approve</a>"
        f"<a class='btn blue' href='/edit/{token}'>Edit</a>"
        f"<a class='btn gray' href='/skip/{token}'>Skip</a></p></div>"
    )

    if run:
        body += _pre("Run", json.dumps({"run_id": run["run_id"], "status": run["status"], "duration_ms": run["duration_ms"]}, indent=2))
        body += _pre("Agent Logs", run["agent_logs_json"])

    body += _pre("Materials", d["materials_json"])
    body += _pre("Topic Plan", d["topic_plan_json"])
    body += _pre("Style Profile", d["style_profile_json"])
    body += _pre("Thread Plan", d["thread_plan_json"])
    body += _pre("Candidates", d["candidates_json"])
    body += _pre("Edited Draft", d["edited_draft_json"])
    body += _pre("Policy Report", d["policy_report_json"])
    body += _pre("Final Text", d["final_text"])
    if d["tweets_json"]:
        body += _pre("Final Tweets", d["tweets_json"])
    if d["published_tweet_ids_json"]:
        body += _pre("Published Tweet IDs", d["published_tweet_ids_json"])
    if d["last_error"]:
        body += _pre("Last Error", d["last_error"])
    return _html("Draft Detail", body)


@router.get("/edit/{token}", response_class=HTMLResponse, dependencies=[_auth_dep()])
def edit_page(token: str):
    conn = get_connection()
    d = conn.execute("SELECT * FROM drafts WHERE token=?", (token,)).fetchone()
    conn.close()
    if not d:
        return _html("Not Found", "<p>draft not found</p>", status_code=404)
    if d["token_consumed"] == 1:
        return _html("Consumed", "<p>token already consumed</p>", status_code=409)

    mode = "thread" if d["thread_enabled"] == 1 else "single"
    tweets = []
    if mode == "thread" and d["tweets_json"]:
        try:
            tweets = json.loads(d["tweets_json"]) or []
        except Exception:
            tweets = []
    if mode == "single":
        tweets = [d["final_text"] or ""]

    textarea_html = ""
    for idx, t in enumerate(tweets, start=1):
        textarea_html += f"""
        <div class='row'>
          <div class='muted'>Tweet {idx} — <span id='count-{idx}'>0</span>/280</div>
          <textarea id='text-{idx}' name='text'>{t}</textarea>
        </div>
        """

    js = """
    <script>
      function bindCount(id, countId) {
        const el = document.getElementById(id);
        const c = document.getElementById(countId);
        const update = () => { c.textContent = el.value.length; };
        el.addEventListener('input', update);
        update();
      }
    </script>
    """
    bind_calls = "".join([f"<script>bindCount('text-{i}','count-{i}');</script>" for i in range(1, len(tweets) + 1)])

    body = f"""
    <div class='card'>
      <p><b>Status:</b> {d['status']} <span class='muted'>(mode={mode})</span></p>
      <form method='post'>
        {textarea_html}
        <div class='row'>
          <button class='btn blue' type='submit'>Save & Check</button>
          <a class='btn green' href='/approve/{token}'>Approve</a>
          <a class='btn gray' href='/draft/{token}'>Details</a>
        </div>
      </form>
      <form method='post' action='/regenerate/{token}' style='margin-top:12px;'>
        <button class='btn gray' type='submit'>Regenerate</button>
      </form>
    </div>
    {js}
    {bind_calls}
    <div class='card'><h3>Policy Report</h3><pre>{d['policy_report_json'] or ''}</pre></div>
    """
    return _html("Edit Draft", body)


@router.post("/edit/{token}", response_class=HTMLResponse, dependencies=[_auth_dep()])
def edit_save(token: str, text: list[str] = Form(...)):
    try:
        code, report = orchestrator.save_edit(token, text)
        return _html("Saved", f"<pre>{report.model_dump_json(indent=2)}</pre><p><a href='/edit/{token}'>Back</a></p>")
    except Exception as e:
        return _html("Error", f"<p>{str(e)}</p>", status_code=400)


@router.post("/regenerate/{token}", response_class=HTMLResponse, dependencies=[_auth_dep()])
def regenerate(token: str):
    code, msg = orchestrator.regenerate(token)
    if code == 200:
        return _html("Regenerated", f"<p>{msg}</p><p><a href='/edit/{token}'>Back to edit</a></p>")
    return _html("Regenerate Failed", f"<p>{msg}</p>", status_code=code)

