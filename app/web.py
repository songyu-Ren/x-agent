import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.config import settings
from app.observability.logging import bind_correlation_ids
from app.observability.metrics import metrics_endpoint_response
from app.orchestrator import orchestrator
from app.runtime_config import get_bool, get_config, get_int, get_str, set_config, set_simple
from app.tasks import run_daily
from infrastructure.db import repositories as db
from infrastructure.db.session import get_sessionmaker

router = APIRouter()


SESSION_COOKIE_NAME = "session_id"
LOGIN_CSRF_COOKIE_NAME = "login_csrf"


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    username: str
    role: str
    session_id: str
    csrf_token: str


def _client_ip(request: Request) -> str | None:
    client = getattr(request, "client", None)
    ip = getattr(client, "host", None) if client else None
    if ip:
        return str(ip)
    return None


def _require_auth(request: Request) -> AuthContext:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    with get_sessionmaker()() as session:
        session_row = db.get_user_session(session, session_id)
        if session_row is None:
            session.commit()
            raise HTTPException(status_code=303, headers={"Location": "/login"})
        user = db.get_user(session, session_row.user_id)
        if user is None:
            db.delete_user_session(session, session_id)
            session.commit()
            raise HTTPException(status_code=303, headers={"Location": "/login"})
        if user.role != "admin":
            raise HTTPException(status_code=403, detail="Forbidden")
        session.commit()
        bind_correlation_ids(user_id=user.id)
        return AuthContext(
            user_id=user.id,
            username=user.username,
            role=user.role,
            session_id=session_row.id,
            csrf_token=session_row.csrf_token,
        )


def _require_api_auth(request: Request) -> AuthContext:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    with get_sessionmaker()() as session:
        session_row = db.get_user_session(session, session_id)
        if session_row is None:
            session.commit()
            raise HTTPException(status_code=401, detail="Unauthorized")
        user = db.get_user(session, session_row.user_id)
        if user is None:
            db.delete_user_session(session, session_id)
            session.commit()
            raise HTTPException(status_code=401, detail="Unauthorized")
        if user.role != "admin":
            raise HTTPException(status_code=403, detail="Forbidden")
        session.commit()
        bind_correlation_ids(user_id=user.id)
        return AuthContext(
            user_id=user.id,
            username=user.username,
            role=user.role,
            session_id=session_row.id,
            csrf_token=session_row.csrf_token,
        )


def _require_api_csrf(request: Request, auth: AuthContext) -> None:
    header_csrf = request.headers.get("x-csrf-token")
    _require_csrf(str(header_csrf or ""), auth.csrf_token)


def _require_csrf(form_token: str | None, expected_token: str) -> None:
    if not form_token:
        raise HTTPException(status_code=403, detail="CSRF token missing")
    if not secrets.compare_digest(str(form_token), str(expected_token)):
        raise HTTPException(status_code=403, detail="CSRF token invalid")


def _audit(
    *,
    auth: AuthContext,
    request: Request,
    action: str,
    draft_id: str | None,
    details: dict,
) -> None:
    with get_sessionmaker()() as session:
        db.add_audit_log(
            session,
            user_id=auth.user_id,
            action=action,
            draft_id=draft_id,
            details=details,
            ip_address=_client_ip(request),
        )
        session.commit()


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


@router.get("/health", tags=["system"], summary="Health check")
def health():
    return {"status": "ok"}


@router.get(
    "/metrics",
    tags=["system"],
    summary="Prometheus metrics",
    description="Prometheus text exposition format.",
)
def metrics():
    if str(getattr(settings, "METRICS_ENABLED", "true")).lower() != "true":
        return JSONResponse({"enabled": False}, status_code=404)
    return metrics_endpoint_response()


@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
def login_page():
    csrf = secrets.token_urlsafe(32)
    body = f"""
    <div class='card'>
      <form method='post' action='/login'>
        <input type='hidden' name='csrf_token' value='{csrf}' />
        <div class='row'>
          <label>Username</label><br/>
          <input name='username' style='width:100%;padding:10px;border-radius:8px;border:1px solid #ddd;' />
        </div>
        <div class='row'>
          <label>Password</label><br/>
          <input type='password' name='password' style='width:100%;padding:10px;border-radius:8px;border:1px solid #ddd;' />
        </div>
        <div class='row'>
          <button class='btn blue' type='submit'>Login</button>
        </div>
      </form>
    </div>
    """
    resp = _html("Login", body)
    resp.set_cookie(
        key=LOGIN_CSRF_COOKIE_NAME,
        value=csrf,
        httponly=False,
        samesite="lax",
        secure=settings.ENV == "production",
        max_age=600,
    )
    return resp


@router.post("/login", response_class=HTMLResponse, include_in_schema=False)
async def login(request: Request):
    form = await request.form()
    cookie_csrf = request.cookies.get(LOGIN_CSRF_COOKIE_NAME)
    _require_csrf(str(form.get("csrf_token") or ""), str(cookie_csrf or ""))
    username = str(form.get("username") or "").strip()
    password = str(form.get("password") or "")
    if not username or not password:
        return _html("Login Failed", "<p class='red'>Missing credentials</p>", status_code=400)

    with get_sessionmaker()() as session:
        user = db.get_user_by_username(session, username)
        if user is None or not db.verify_password(password, user.password_hash):
            return _html(
                "Login Failed", "<p class='red'>Invalid username or password</p>", status_code=401
            )
        ttl_hours = int(getattr(settings, "SESSION_TTL_HOURS", 24) or 24)
        now = datetime.now(UTC)
        session_id = str(uuid.uuid4())
        csrf_token = secrets.token_urlsafe(32)
        db.create_user_session(
            session,
            session_id=session_id,
            user_id=user.id,
            csrf_token=csrf_token,
            created_at=now,
            expires_at=now + timedelta(hours=ttl_hours),
            ip_address=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
        db.add_audit_log(
            session,
            user_id=user.id,
            action="login",
            draft_id=None,
            details={"username": username},
            ip_address=_client_ip(request),
        )
        session.commit()

    resp = _html("Login", "<p>Logged in. <a href='/drafts'>Go to drafts</a></p>")
    resp.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        samesite="lax",
        secure=settings.ENV == "production",
        max_age=ttl_hours * 3600,
    )
    resp.delete_cookie(LOGIN_CSRF_COOKIE_NAME)
    return resp


@router.post("/logout", response_class=HTMLResponse, include_in_schema=False)
async def logout(request: Request, auth: Annotated[AuthContext, Depends(_require_auth)]):
    form = await request.form()
    _require_csrf(str(form.get("csrf_token") or ""), auth.csrf_token)
    with get_sessionmaker()() as session:
        db.delete_user_session(session, auth.session_id)
        db.add_audit_log(
            session,
            user_id=auth.user_id,
            action="logout",
            draft_id=None,
            details={},
            ip_address=_client_ip(request),
        )
        session.commit()
    resp = _html("Logout", "<p>Logged out. <a href='/login'>Login</a></p>")
    resp.delete_cookie(SESSION_COOKIE_NAME)
    return resp


@router.get("/api/health", tags=["system"], summary="Health check (API)")
def api_health():
    return {"status": "ok"}


@router.get(
    "/api/metrics",
    tags=["system"],
    summary="Prometheus metrics (API)",
    description="Prometheus text exposition format.",
)
def api_metrics():
    if str(getattr(settings, "METRICS_ENABLED", "true")).lower() != "true":
        return JSONResponse({"enabled": False}, status_code=404)
    return metrics_endpoint_response()


@router.get("/api/auth/csrf", tags=["auth"], summary="Issue login CSRF cookie")
def api_auth_csrf():
    csrf = secrets.token_urlsafe(32)
    resp = JSONResponse({"csrf_token": csrf})
    resp.set_cookie(
        key=LOGIN_CSRF_COOKIE_NAME,
        value=csrf,
        httponly=False,
        samesite="lax",
        secure=settings.ENV == "production",
        max_age=600,
    )
    return resp


@router.post("/api/auth/login", tags=["auth"], summary="Login (API)")
async def api_auth_login(request: Request):
    data = await request.json()
    cookie_csrf = request.cookies.get(LOGIN_CSRF_COOKIE_NAME)
    _require_csrf(str(data.get("csrf_token") or ""), str(cookie_csrf or ""))
    username = str(data.get("username") or "").strip()
    password = str(data.get("password") or "")
    if not username or not password:
        raise HTTPException(status_code=400, detail="Missing credentials")

    user_id: str
    user_username: str
    user_role: str
    with get_sessionmaker()() as session:
        user = db.get_user_by_username(session, username)
        if user is None or not db.verify_password(password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid username or password")
        ttl_hours = int(getattr(settings, "SESSION_TTL_HOURS", 24) or 24)
        now = datetime.now(UTC)
        session_id = str(uuid.uuid4())
        csrf_token = secrets.token_urlsafe(32)
        user_id = str(user.id)
        user_username = str(user.username)
        user_role = str(user.role)
        db.create_user_session(
            session,
            session_id=session_id,
            user_id=user_id,
            csrf_token=csrf_token,
            created_at=now,
            expires_at=now + timedelta(hours=ttl_hours),
            ip_address=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
        db.add_audit_log(
            session,
            user_id=user.id,
            action="login",
            draft_id=None,
            details={"username": username, "via": "api"},
            ip_address=_client_ip(request),
        )
        session.commit()

    resp = JSONResponse(
        {
            "ok": True,
            "user": {"id": user_id, "username": user_username, "role": user_role},
            "csrf_token": csrf_token,
        }
    )
    resp.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        samesite="lax",
        secure=settings.ENV == "production",
        max_age=ttl_hours * 3600,
    )
    resp.delete_cookie(LOGIN_CSRF_COOKIE_NAME)
    return resp


@router.post("/api/auth/logout", tags=["auth"], summary="Logout (API)")
async def api_auth_logout(
    request: Request, auth: Annotated[AuthContext, Depends(_require_api_auth)]
):
    _require_api_csrf(request, auth)
    with get_sessionmaker()() as session:
        db.delete_user_session(session, auth.session_id)
        db.add_audit_log(
            session,
            user_id=auth.user_id,
            action="logout",
            draft_id=None,
            details={"via": "api"},
            ip_address=_client_ip(request),
        )
        session.commit()
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(SESSION_COOKIE_NAME)
    return resp


@router.get("/api/auth/me", tags=["auth"], summary="Current user (API)")
def api_auth_me(auth: Annotated[AuthContext, Depends(_require_api_auth)]):
    return {
        "user": {"id": auth.user_id, "username": auth.username, "role": auth.role},
        "csrf_token": auth.csrf_token,
    }


@router.get("/api/drafts", tags=["drafts"], summary="List drafts")
def api_list_drafts(
    auth: Annotated[AuthContext, Depends(_require_api_auth)],
    status: str | None = Query(default=None),
    days: int = Query(default=14, ge=1, le=365),
    limit: int = Query(default=200, ge=1, le=500),
):
    since = datetime.now(UTC) - timedelta(days=int(days))
    with get_sessionmaker()() as session:
        rows = db.list_drafts(session, since=since, status_filter=status, limit=limit)
    return {
        "items": [
            {
                "id": draft_id,
                "created_at": created_at.isoformat(),
                "status": st,
                "final_text": final_text,
                "char_count": len(final_text or ""),
            }
            for (draft_id, created_at, st, final_text) in rows
        ]
    }


@router.get("/api/drafts/{draft_id}", tags=["drafts"], summary="Draft detail")
def api_draft_detail(draft_id: str, auth: Annotated[AuthContext, Depends(_require_api_auth)]):
    with get_sessionmaker()() as session:
        d = db.get_draft(session, draft_id)
        if d is None:
            raise HTTPException(status_code=404, detail="Not found")
        run = db.get_run(session, d.run_id) if d.run_id else None
        agent_logs = db.get_agent_logs_for_run(session, d.run_id) if d.run_id else []

    tweets = list(d.tweets_json or []) if d.thread_enabled else []
    char_count = sum(len(t) for t in tweets) if tweets else len(d.final_text or "")

    return {
        "draft": {
            "id": d.id,
            "run_id": d.run_id,
            "created_at": d.created_at.isoformat(),
            "expires_at": d.expires_at.isoformat(),
            "status": d.status,
            "thread_enabled": bool(d.thread_enabled),
            "final_text": d.final_text or "",
            "tweets": tweets if tweets else None,
            "char_count": char_count,
            "materials": d.materials_json,
            "topic_plan": d.topic_plan_json,
            "style_profile": d.style_profile_json,
            "candidates": d.candidates_json,
            "edited_draft": d.edited_draft_json,
            "policy_report": d.policy_report_json,
            "published_tweet_ids": d.published_tweet_ids_json,
            "last_error": d.last_error,
        },
        "run": (
            None
            if run is None
            else {
                "run_id": run.run_id,
                "source": run.source,
                "status": run.status,
                "created_at": run.created_at.isoformat(),
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                "duration_ms": run.duration_ms,
                "last_error": run.last_error,
            }
        ),
        "agent_logs": [
            {
                "id": log.id,
                "agent_name": log.agent_name,
                "start_ts": log.start_ts.isoformat(),
                "end_ts": log.end_ts.isoformat(),
                "duration_ms": log.duration_ms,
                "input_summary": log.input_summary,
                "output_summary": log.output_summary,
                "model_used": log.model_used,
                "errors": log.errors,
                "warnings": list(log.warnings_json or []),
            }
            for log in agent_logs
        ],
    }


@router.post("/api/drafts/{draft_id}/edit", tags=["drafts"], summary="Edit draft text")
async def api_edit_draft(
    draft_id: str,
    request: Request,
    auth: Annotated[AuthContext, Depends(_require_api_auth)],
):
    _require_api_csrf(request, auth)
    data = await request.json()
    texts = data.get("texts")
    save = bool(data.get("save", True))
    if not isinstance(texts, list) or any(not isinstance(t, str) for t in texts):
        raise HTTPException(status_code=400, detail="texts must be a list of strings")
    if save:
        code, report = orchestrator.save_edit_by_id(draft_id, [str(t) for t in texts])
    else:
        code, report = orchestrator.policy_check_by_id(draft_id, [str(t) for t in texts])
    _audit(
        auth=auth,
        request=request,
        action=("edit" if save else "policy_check"),
        draft_id=draft_id,
        details={
            "status_code": code,
            "risk_level": report.risk_level,
            "action_result": report.action,
        },
    )
    return {"status_code": code, "policy_report": report.model_dump(mode="json")}


@router.post("/api/drafts/{draft_id}/approve", tags=["drafts"], summary="Approve draft")
async def api_approve_draft(
    draft_id: str, request: Request, auth: Annotated[AuthContext, Depends(_require_api_auth)]
):
    _require_api_csrf(request, auth)
    code, msg = orchestrator.approve_draft_by_id(draft_id)
    _audit(
        auth=auth,
        request=request,
        action="approve",
        draft_id=draft_id,
        details={"status_code": code, "message": msg[:200]},
    )
    return JSONResponse({"status_code": code, "message": msg}, status_code=code)


@router.post("/api/drafts/{draft_id}/skip", tags=["drafts"], summary="Skip draft")
async def api_skip_draft(
    draft_id: str, request: Request, auth: Annotated[AuthContext, Depends(_require_api_auth)]
):
    _require_api_csrf(request, auth)
    code, msg = orchestrator.skip_draft_by_id(draft_id)
    _audit(
        auth=auth,
        request=request,
        action="skip",
        draft_id=draft_id,
        details={"status_code": code, "message": msg[:200]},
    )
    return JSONResponse({"status_code": code, "message": msg}, status_code=code)


@router.post("/api/drafts/{draft_id}/regenerate", tags=["drafts"], summary="Regenerate draft")
async def api_regenerate_draft(
    draft_id: str, request: Request, auth: Annotated[AuthContext, Depends(_require_api_auth)]
):
    _require_api_csrf(request, auth)
    code, msg = orchestrator.regenerate_by_id(draft_id)
    _audit(
        auth=auth,
        request=request,
        action="regenerate",
        draft_id=draft_id,
        details={"status_code": code, "message": msg[:200]},
    )
    return JSONResponse({"status_code": code, "message": msg}, status_code=code)


@router.post("/api/drafts/{draft_id}/resume", tags=["drafts"], summary="Resume publish attempt")
async def api_resume_draft(
    draft_id: str, request: Request, auth: Annotated[AuthContext, Depends(_require_api_auth)]
):
    _require_api_csrf(request, auth)
    code, msg = orchestrator.resume_publish_by_id(draft_id)
    _audit(
        auth=auth,
        request=request,
        action="resume",
        draft_id=draft_id,
        details={"status_code": code, "message": msg[:200]},
    )
    return JSONResponse({"status_code": code, "message": msg}, status_code=code)


@router.get("/api/runs", tags=["runs"], summary="List runs")
def api_list_runs(
    auth: Annotated[AuthContext, Depends(_require_api_auth)],
    days: int = Query(default=14, ge=1, le=365),
    limit: int = Query(default=200, ge=1, le=500),
):
    since = datetime.now(UTC) - timedelta(days=int(days))
    with get_sessionmaker()() as session:
        rows = db.list_runs(session, since=since, limit=limit)
    return {
        "items": [
            {
                "run_id": run_id,
                "status": status,
                "created_at": created_at.isoformat(),
                "finished_at": finished_at.isoformat() if finished_at else None,
                "duration_ms": duration_ms,
                "last_error": last_error,
            }
            for (run_id, status, created_at, finished_at, duration_ms, last_error) in rows
        ]
    }


@router.get("/api/settings", tags=["settings"], summary="Get runtime settings")
def api_get_settings(auth: Annotated[AuthContext, Depends(_require_api_auth)]):
    blocked_raw = get_config("blocked_terms") or {}
    blocked = blocked_raw.get("value")
    blocked_terms = [str(t).strip() for t in blocked] if isinstance(blocked, list) else []
    return {
        "schedule": {
            "hour": get_int("schedule_hour", settings.SCHEDULE_HOUR),
            "minute": get_int("schedule_minute", settings.SCHEDULE_MINUTE),
            "timezone": get_str("timezone", settings.TIMEZONE),
        },
        "thread": {
            "enabled": get_bool("thread_enabled", settings.THREAD_ENABLED),
            "max_tweets": get_int("thread_max_tweets", settings.THREAD_MAX_TWEETS),
            "numbering_enabled": get_bool(
                "thread_numbering_enabled", settings.THREAD_NUMBERING_ENABLED
            ),
        },
        "blocked_terms": blocked_terms,
    }


@router.post("/api/settings", tags=["settings"], summary="Update runtime settings")
async def api_set_settings(
    request: Request, auth: Annotated[AuthContext, Depends(_require_api_auth)]
):
    _require_api_csrf(request, auth)
    data = await request.json()

    schedule = data.get("schedule")
    if isinstance(schedule, dict):
        if "hour" in schedule:
            set_simple("schedule_hour", int(schedule["hour"]))
        if "minute" in schedule:
            set_simple("schedule_minute", int(schedule["minute"]))
        if "timezone" in schedule:
            tz = str(schedule["timezone"] or "").strip()
            if tz:
                set_simple("timezone", tz)

    thread = data.get("thread")
    if isinstance(thread, dict):
        if "enabled" in thread:
            set_simple("thread_enabled", bool(thread["enabled"]))
        if "max_tweets" in thread:
            set_simple("thread_max_tweets", int(thread["max_tweets"]))
        if "numbering_enabled" in thread:
            set_simple("thread_numbering_enabled", bool(thread["numbering_enabled"]))

    if "blocked_terms" in data:
        terms = data.get("blocked_terms")
        if not isinstance(terms, list) or any(not isinstance(t, str) for t in terms):
            raise HTTPException(status_code=400, detail="blocked_terms must be a list of strings")
        cleaned = [str(t).strip().lower() for t in terms if str(t).strip()]
        set_config(
            "blocked_terms",
            {
                "value": sorted(set(cleaned)),
                "updated_at": datetime.now(UTC).isoformat(),
            },
        )

    return api_get_settings(auth)


@router.post(
    "/generate-now",
    tags=["runs"],
    summary="Enqueue a manual run",
    description="Creates a run_id and enqueues a Celery job to execute the workflow.",
)
async def generate_now(request: Request, auth: Annotated[AuthContext, Depends(_require_auth)]):
    header_csrf = request.headers.get("x-csrf-token")
    _require_csrf(str(header_csrf or ""), auth.csrf_token)
    run_id = str(uuid.uuid4())
    bind_correlation_ids(run_id=run_id, user_id=auth.user_id)
    result = run_daily.delay(
        run_id=run_id,
        source="manual",
        request_id=request.headers.get("x-request-id"),
        user_id=auth.user_id,
    )
    _audit(
        auth=auth,
        request=request,
        action="generate_now",
        draft_id=None,
        details={"run_id": run_id, "task_id": str(result.id)},
    )
    return {"message": "enqueued", "run_id": run_id, "task_id": result.id}


@router.get("/approve/{token}", response_class=HTMLResponse, include_in_schema=False)
def approve(token: str, request: Request, auth: Annotated[AuthContext, Depends(_require_auth)]):
    with get_sessionmaker()() as session:
        draft, _, token_status = db.resolve_action_token(session, action="approve", raw_token=token)
        draft_id = draft.id if token_status == "ok" and draft is not None else None
        run_id = draft.run_id if token_status == "ok" and draft is not None else None
    bind_correlation_ids(run_id=run_id, draft_id=draft_id, user_id=auth.user_id)
    code, msg = orchestrator.approve_draft(token)
    _audit(
        auth=auth,
        request=request,
        action="approve",
        draft_id=draft_id,
        details={"status_code": code, "message": msg[:200]},
    )
    if code == 200:
        return _html("Approve", f"<div class='card'><p>{msg}</p></div>")
    if code == 410:
        return _html("Expired", "<p class='red'>Token expired (410)</p>", status_code=410)
    return _html("Approve Failed", f"<p class='red'>{msg}</p>", status_code=code)


@router.get("/skip/{token}", response_class=HTMLResponse, include_in_schema=False)
def skip(token: str, request: Request, auth: Annotated[AuthContext, Depends(_require_auth)]):
    with get_sessionmaker()() as session:
        draft, _, token_status = db.resolve_action_token(session, action="skip", raw_token=token)
        draft_id = draft.id if token_status == "ok" and draft is not None else None
        run_id = draft.run_id if token_status == "ok" and draft is not None else None
    bind_correlation_ids(run_id=run_id, draft_id=draft_id, user_id=auth.user_id)
    code, msg = orchestrator.skip_draft(token)
    _audit(
        auth=auth,
        request=request,
        action="skip",
        draft_id=draft_id,
        details={"status_code": code, "message": msg[:200]},
    )
    return _html("Skip", f"<p>{msg}</p>", status_code=code)


@router.get("/drafts", response_class=HTMLResponse, include_in_schema=False)
def drafts_page(
    auth: Annotated[AuthContext, Depends(_require_auth)],
    status_filter: str | None = Query(default=None, alias="status"),
):
    since = datetime.now(UTC) - timedelta(days=14)
    with get_sessionmaker()() as session:
        rows = db.list_drafts(session, since=since, status_filter=status_filter, limit=200)
    items = []
    for draft_id, created_at_dt, st, final_text in rows:
        created_at = str(created_at_dt)[:16]
        preview = (final_text or "")[:80]
        items.append(
            f"<li><code>{created_at}</code> <b>{st}</b> — {preview} <a href='/draft-id/{draft_id}'>details</a> <a href='/edit-id/{draft_id}'>edit</a></li>"
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


@router.get("/draft/{token}", response_class=HTMLResponse, include_in_schema=False)
def draft_detail(token: str, auth: Annotated[AuthContext, Depends(_require_auth)]):
    with get_sessionmaker()() as session:
        d, _, token_status = db.resolve_action_token(session, action="view", raw_token=token)
        if token_status == "expired":
            return _html("Expired", "<p class='red'>Token expired (410)</p>", status_code=410)
        if token_status != "ok" or d is None:
            return _html("Not Found", "<p>draft not found</p>", status_code=404)
        run = db.get_run(session, d.run_id) if d.run_id else None
        agent_logs = db.get_agent_logs_for_run(session, d.run_id) if d.run_id else []
        ttl_seconds = max(0, int((d.expires_at - datetime.now(UTC)).total_seconds()))
        approve_token = db.issue_action_token(
            session=session, draft=d, action="approve", ttl_seconds=ttl_seconds, one_time=True
        )
        edit_token = db.issue_action_token(
            session=session, draft=d, action="edit", ttl_seconds=ttl_seconds, one_time=False
        )
        skip_token = db.issue_action_token(
            session=session, draft=d, action="skip", ttl_seconds=ttl_seconds, one_time=True
        )
        session.commit()

    def _pre(title: str, value: str | None):
        return f"<div class='card'><h3>{title}</h3><pre>{value or ''}</pre></div>"

    body = (
        f"<div class='card'><p><b>Status:</b> {d.status}</p>"
        f"<p><b>Draft ID:</b> <code>{d.id}</code></p>"
        f"<p><a class='btn green' href='/approve/{approve_token}'>Approve</a>"
        f"<a class='btn blue' href='/edit/{edit_token}'>Edit</a>"
        f"<a class='btn gray' href='/skip/{skip_token}'>Skip</a></p></div>"
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


@router.get("/edit/{token}", response_class=HTMLResponse, include_in_schema=False)
def edit_page(token: str, auth: Annotated[AuthContext, Depends(_require_auth)]):
    with get_sessionmaker()() as session:
        d, _, token_status = db.resolve_action_token(session, action="edit", raw_token=token)
        regenerate_token = ""
        if token_status == "ok" and d is not None:
            ttl_seconds = max(0, int((d.expires_at - datetime.now(UTC)).total_seconds()))
            regenerate_token = db.issue_action_token(
                session=session,
                draft=d,
                action="regenerate",
                ttl_seconds=ttl_seconds,
                one_time=False,
            )
            session.commit()
    if token_status == "expired":
        return _html("Expired", "<p class='red'>Token expired (410)</p>", status_code=410)
    if token_status != "ok" or d is None:
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
        <input type='hidden' name='csrf_token' value='{auth.csrf_token}' />
        {textarea_html}
        <div class='row'>
          <button class='btn blue' type='submit'>Save & Check</button>
          <a class='btn gray' href='/draft-id/{d.id}'>Details</a>
        </div>
      </form>
      <form method='post' action='/regenerate/{regenerate_token}' style='margin-top:12px;'>
        <input type='hidden' name='csrf_token' value='{auth.csrf_token}' />
        <button class='btn gray' type='submit'>Regenerate</button>
      </form>
    </div>
    {js}
    {bind_calls}
    <div class='card'><h3>Policy Report</h3><pre>{json.dumps(d.policy_report_json, indent=2) if d.policy_report_json else ""}</pre></div>
    """
    return _html("Edit Draft", body)


@router.post("/edit/{token}", response_class=HTMLResponse, include_in_schema=False)
async def edit_save(
    token: str, request: Request, auth: Annotated[AuthContext, Depends(_require_auth)]
):
    try:
        form = await request.form()
        _require_csrf(str(form.get("csrf_token") or ""), auth.csrf_token)
        texts = form.getlist("text")
        code, report = orchestrator.save_edit(token, [str(t) for t in texts])
        with get_sessionmaker()() as session:
            draft, _, token_status = db.resolve_action_token(
                session, action="edit", raw_token=token
            )
            draft_id = draft.id if token_status == "ok" and draft is not None else None
        _audit(
            auth=auth,
            request=request,
            action="edit",
            draft_id=draft_id,
            details={
                "status_code": code,
                "risk_level": str(report.risk_level),
                "action": str(report.action),
            },
        )
        return _html(
            "Saved",
            f"<pre>{report.model_dump_json(indent=2)}</pre><p><a href='/edit/{token}'>Back</a></p>",
        )
    except Exception as e:
        return _html("Error", f"<p>{e!s}</p>", status_code=400)


@router.post("/regenerate/{token}", response_class=HTMLResponse, include_in_schema=False)
async def regenerate(
    token: str, request: Request, auth: Annotated[AuthContext, Depends(_require_auth)]
):
    form = await request.form()
    _require_csrf(str(form.get("csrf_token") or ""), auth.csrf_token)
    with get_sessionmaker()() as session:
        draft, _, token_status = db.resolve_action_token(
            session, action="regenerate", raw_token=token
        )
        draft_id = draft.id if token_status == "ok" and draft is not None else None
    code, msg = orchestrator.regenerate(token)
    _audit(
        auth=auth,
        request=request,
        action="regenerate",
        draft_id=draft_id,
        details={"status_code": code, "message": msg[:200]},
    )
    if code == 200:
        return _html("Regenerated", f"<p>{msg}</p><p><a href='/edit/{token}'>Back to edit</a></p>")
    return _html("Regenerate Failed", f"<p>{msg}</p>", status_code=code)


@router.get("/draft-id/{draft_id}", response_class=HTMLResponse, include_in_schema=False)
def draft_detail_by_id(draft_id: str, auth: Annotated[AuthContext, Depends(_require_auth)]):
    with get_sessionmaker()() as session:
        d = db.get_draft(session, draft_id)
        if not d:
            return _html("Not Found", "<p>draft not found</p>", status_code=404)
        run = db.get_run(session, d.run_id) if d.run_id else None
        agent_logs = db.get_agent_logs_for_run(session, d.run_id) if d.run_id else []

    def _pre(title: str, value: str | None):
        return f"<div class='card'><h3>{title}</h3><pre>{value or ''}</pre></div>"

    body = f"<div class='card'><p><b>Status:</b> {d.status}</p><p><b>Draft ID:</b> <code>{d.id}</code></p></div>"

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


@router.get("/edit-id/{draft_id}", response_class=HTMLResponse, include_in_schema=False)
def edit_page_by_id(draft_id: str, auth: Annotated[AuthContext, Depends(_require_auth)]):
    with get_sessionmaker()() as session:
        d = db.get_draft(session, draft_id)
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
        <input type='hidden' name='csrf_token' value='{auth.csrf_token}' />
        {textarea_html}
        <div class='row'>
          <button class='btn blue' type='submit'>Save & Check</button>
          <a class='btn gray' href='/draft-id/{draft_id}'>Details</a>
        </div>
      </form>
      <form method='post' action='/regenerate-id/{draft_id}' style='margin-top:12px;'>
        <input type='hidden' name='csrf_token' value='{auth.csrf_token}' />
        <button class='btn gray' type='submit'>Regenerate</button>
      </form>
    </div>
    {js}
    {bind_calls}
    <div class='card'><h3>Policy Report</h3><pre>{json.dumps(d.policy_report_json, indent=2) if d.policy_report_json else ""}</pre></div>
    """
    return _html("Edit Draft", body)


@router.post("/edit-id/{draft_id}", response_class=HTMLResponse, include_in_schema=False)
async def edit_save_by_id(
    draft_id: str, request: Request, auth: Annotated[AuthContext, Depends(_require_auth)]
):
    try:
        form = await request.form()
        _require_csrf(str(form.get("csrf_token") or ""), auth.csrf_token)
        texts = form.getlist("text")
        with get_sessionmaker()() as session:
            draft = db.get_draft(session, draft_id)
        if draft is None:
            return _html("Not Found", "<p>draft not found</p>", status_code=404)
        code, report = orchestrator.save_edit_by_id(draft_id, [str(t) for t in texts])
        _audit(
            auth=auth,
            request=request,
            action="edit",
            draft_id=draft_id,
            details={
                "status_code": code,
                "risk_level": str(report.risk_level),
                "action": str(report.action),
            },
        )
        return _html(
            "Saved",
            f"<pre>{report.model_dump_json(indent=2)}</pre><p><a href='/edit-id/{draft_id}'>Back</a></p>",
        )
    except Exception as e:
        return _html("Error", f"<p>{e!s}</p>", status_code=400)


@router.post("/regenerate-id/{draft_id}", response_class=HTMLResponse, include_in_schema=False)
async def regenerate_by_id(
    draft_id: str, request: Request, auth: Annotated[AuthContext, Depends(_require_auth)]
):
    form = await request.form()
    _require_csrf(str(form.get("csrf_token") or ""), auth.csrf_token)
    code, msg = orchestrator.regenerate_by_id(draft_id)
    _audit(
        auth=auth,
        request=request,
        action="regenerate",
        draft_id=draft_id,
        details={"status_code": code, "message": msg[:200]},
    )
    if code == 200:
        return _html(
            "Regenerated",
            f"<p>{msg}</p><p><a href='/edit-id/{draft_id}'>Back to edit</a></p>",
        )
    return _html("Regenerate Failed", f"<p>{msg}</p>", status_code=code)
