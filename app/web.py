import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic

from app.config import settings
from app.observability.metrics import metrics_endpoint_response
from app.orchestrator import orchestrator
from app.tasks import run_daily
from infrastructure.db.repositories import (
    get_agent_logs_for_run,
    get_draft_by_token,
    get_run,
)
from infrastructure.db.repositories import (
    list_drafts as list_drafts_repo,
)
from infrastructure.db.session import get_sessionmaker

router = APIRouter()
security = HTTPBasic()


async def _require_basic(request: Request):
    credentials = await security(request)
    if not settings.BASIC_AUTH_USER or not settings.BASIC_AUTH_PASS:
        return "anonymous"
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )

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
    return Depends(lambda: None)


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
    return metrics_endpoint_response()


@router.post("/generate-now", dependencies=[_auth_dep()])
async def generate_now():
    run_id = str(uuid.uuid4())
    result = run_daily.delay(run_id=run_id, source="manual")
    return {"message": "enqueued", "run_id": run_id, "task_id": result.id}


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
def drafts_page(status_filter: str | None = Query(default=None, alias="status")):
    since = datetime.now(UTC) - timedelta(days=14)
    with get_sessionmaker()() as session:
        rows = list_drafts_repo(session, since=since, status_filter=status_filter, limit=200)
    items = []
    for token, created_at_dt, st, final_text in rows:
        created_at = str(created_at_dt)[:16]
        preview = (final_text or "")[:80]
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
    with get_sessionmaker()() as session:
        d = get_draft_by_token(session, token)
        if not d:
            return _html("Not Found", "<p>draft not found</p>", status_code=404)
        run = get_run(session, d.run_id) if d.run_id else None
        agent_logs = get_agent_logs_for_run(session, d.run_id) if d.run_id else []

    def _pre(title: str, value: str | None):
        return f"<div class='card'><h3>{title}</h3><pre>{value or ''}</pre></div>"

    body = (
        f"<div class='card'><p><b>Status:</b> {d.status}</p>"
        f"<p><b>Token:</b> <code>{d.token}</code></p>"
        f"<p><a class='btn green' href='/approve/{token}'>Approve</a>"
        f"<a class='btn blue' href='/edit/{token}'>Edit</a>"
        f"<a class='btn gray' href='/skip/{token}'>Skip</a></p></div>"
    )

    if run:
        body += _pre(
            "Run",
            json.dumps(
                {
                    "run_id": run.run_id,
                    "status": run.status,
                    "duration_ms": run.duration_ms,
                },
                indent=2,
            ),
        )
        body += _pre(
            "Agent Logs",
            json.dumps(
                [
                    {
                        "agent_name": log_item.agent_name,
                        "start_ts": log_item.start_ts.isoformat(),
                        "end_ts": log_item.end_ts.isoformat(),
                        "duration_ms": log_item.duration_ms,
                        "input_summary": log_item.input_summary,
                        "output_summary": log_item.output_summary,
                        "model_used": log_item.model_used,
                        "errors": log_item.errors,
                        "warnings": log_item.warnings_json,
                    }
                    for log_item in agent_logs
                ],
                indent=2,
            ),
        )

    body += _pre("Materials", json.dumps(d.materials_json, indent=2))
    body += _pre("Topic Plan", json.dumps(d.topic_plan_json, indent=2))
    body += _pre("Style Profile", json.dumps(d.style_profile_json, indent=2))
    body += _pre(
        "Thread Plan", json.dumps(d.thread_plan_json, indent=2) if d.thread_plan_json else ""
    )
    body += _pre("Candidates", json.dumps(d.candidates_json, indent=2))
    body += _pre("Edited Draft", json.dumps(d.edited_draft_json, indent=2))
    body += _pre("Policy Report", json.dumps(d.policy_report_json, indent=2))
    body += _pre("Final Text", d.final_text)
    if d.tweets_json:
        body += _pre("Final Tweets", json.dumps(d.tweets_json, indent=2))
    if d.published_tweet_ids_json:
        body += _pre("Published Tweet IDs", json.dumps(d.published_tweet_ids_json, indent=2))
    if d.last_error:
        body += _pre("Last Error", d.last_error)
    return _html("Draft Detail", body)


@router.get("/edit/{token}", response_class=HTMLResponse, dependencies=[_auth_dep()])
def edit_page(token: str):
    with get_sessionmaker()() as session:
        d = get_draft_by_token(session, token)
    if d is None:
        return _html("Not Found", "<p>draft not found</p>", status_code=404)
    if d.token_consumed:
        return _html("Consumed", "<p>token already consumed</p>", status_code=409)

    mode = "thread" if d.thread_enabled else "single"
    tweets: list[str] = []
    if mode == "thread" and d.tweets_json:
        try:
            tweets = (
                [str(item) for item in d.tweets_json] if isinstance(d.tweets_json, list) else []
            )
        except Exception:
            tweets = []
    if mode == "single":
        tweets = [str(d.final_text or "")]

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
    bind_calls = "".join(
        [f"<script>bindCount('text-{i}','count-{i}');</script>" for i in range(1, len(tweets) + 1)]
    )

    body = f"""
    <div class='card'>
      <p><b>Status:</b> {d.status} <span class='muted'>(mode={mode})</span></p>
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
    <div class='card'><h3>Policy Report</h3><pre>{json.dumps(d.policy_report_json, indent=2) if d.policy_report_json else ''}</pre></div>
    """
    return _html("Edit Draft", body)


@router.post("/edit/{token}", response_class=HTMLResponse, dependencies=[_auth_dep()])
async def edit_save(token: str, request: Request):
    try:
        form = await request.form()
        texts = form.getlist("text")
        code, report = orchestrator.save_edit(token, [str(t) for t in texts])
        return _html(
            "Saved",
            f"<pre>{report.model_dump_json(indent=2)}</pre><p><a href='/edit/{token}'>Back</a></p>",
        )
    except Exception as e:
        return _html("Error", f"<p>{e!s}</p>", status_code=400)


@router.post("/regenerate/{token}", response_class=HTMLResponse, dependencies=[_auth_dep()])
def regenerate(token: str):
    code, msg = orchestrator.regenerate(token)
    if code == 200:
        return _html("Regenerated", f"<p>{msg}</p><p><a href='/edit/{token}'>Back to edit</a></p>")
    return _html("Regenerate Failed", f"<p>{msg}</p>", status_code=code)
