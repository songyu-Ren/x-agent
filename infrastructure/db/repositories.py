from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from domain.models import (
    AgentLog as AgentLogModel,
)
from domain.models import (
    DraftCandidates,
    EditedDraft,
    Materials,
    PolicyReport,
    StyleProfile,
    ThreadPlan,
    TopicPlan,
    WeeklyReport,
)
from infrastructure.db import models


def _as_utc_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def get_run(session: Session, run_id: str) -> models.Run | None:
    return session.get(models.Run, run_id)


def create_run(session: Session, run_id: str, source: str, created_at: datetime) -> None:
    if session.get(models.Run, run_id) is not None:
        return
    session.add(models.Run(run_id=run_id, source=source, status="running", created_at=created_at))


def list_runs(
    session: Session, since: datetime, limit: int = 200
) -> list[tuple[str, str, datetime, datetime | None, int | None, str | None]]:
    stmt: Select[tuple[models.Run]] = (
        select(models.Run)
        .where(models.Run.created_at >= since)
        .order_by(models.Run.created_at.desc())
        .limit(limit)
    )
    rows = list(session.execute(stmt).scalars().all())
    return [
        (
            str(r.run_id),
            str(r.status),
            r.created_at,
            r.finished_at,
            int(r.duration_ms) if r.duration_ms is not None else None,
            str(r.last_error) if r.last_error else None,
        )
        for r in rows
    ]


def update_run_status(
    session: Session,
    run_id: str,
    status: str,
    finished_at: datetime,
    duration_ms: int | None,
    last_error: str | None,
) -> None:
    run = session.get(models.Run, run_id)
    if run is None:
        return
    run.status = status
    run.finished_at = finished_at
    run.duration_ms = duration_ms
    run.last_error = last_error[:500] if last_error else None


def add_agent_log(session: Session, run_id: str, log: AgentLogModel) -> None:
    session.add(
        models.AgentLog(
            run_id=run_id,
            agent_name=log.agent_name,
            start_ts=log.start_ts,
            end_ts=log.end_ts,
            duration_ms=log.duration_ms,
            input_summary=log.input_summary[:200],
            output_summary=log.output_summary[:200],
            model_used=log.model_used,
            errors=log.errors[:500] if log.errors else None,
            warnings_json=list(log.warnings or []),
        )
    )


def create_draft(
    session: Session,
    run_id: str,
    draft_id: str,
    token_hash: str,
    created_at: datetime,
    expires_at: datetime,
    status: str,
    materials: Materials,
    topic_plan: TopicPlan,
    style_profile: StyleProfile,
    thread_plan: ThreadPlan,
    candidates: DraftCandidates,
    edited_draft: EditedDraft,
    policy_report: PolicyReport,
) -> models.Draft:
    existing = session.get(models.Draft, draft_id)
    if existing is not None:
        return existing
    thread_plan_json = thread_plan.model_dump(mode="json") if thread_plan else None
    tweets_json = edited_draft.final_tweets if edited_draft.mode == "thread" else None
    final_text = edited_draft.final_text or (tweets_json[0] if tweets_json else "")
    d = models.Draft(
        id=draft_id,
        token=token_hash,
        run_id=run_id,
        created_at=created_at,
        expires_at=expires_at,
        status=status,
        token_consumed=False,
        thread_enabled=edited_draft.mode == "thread",
        thread_plan_json=thread_plan_json,
        tweets_json=tweets_json,
        materials_json=materials.model_dump(mode="json"),
        topic_plan_json=topic_plan.model_dump(mode="json"),
        style_profile_json=style_profile.model_dump(mode="json"),
        candidates_json=candidates.model_dump(mode="json"),
        edited_draft_json=edited_draft.model_dump(mode="json"),
        policy_report_json=policy_report.model_dump(mode="json"),
        final_text=final_text,
        published_tweet_ids_json=None,
        last_error=None,
        approval_idempotency_key=None,
    )
    session.add(d)
    session.add(
        models.PolicyReport(
            draft_id=draft_id,
            created_at=created_at,
            action=str(policy_report.action),
            risk_level=str(policy_report.risk_level),
            report_json=policy_report.model_dump(mode="json"),
        )
    )
    return d


def get_draft(session: Session, draft_id: str) -> models.Draft | None:
    return session.get(models.Draft, draft_id)


def list_drafts(
    session: Session, since: datetime, status_filter: str | None, limit: int = 200
) -> list[tuple[str, datetime, str, str]]:
    stmt = (
        select(
            models.Draft.id,
            models.Draft.created_at,
            models.Draft.status,
            models.Draft.final_text,
        )
        .where(models.Draft.created_at >= since)
        .order_by(models.Draft.created_at.desc())
        .limit(limit)
    )
    if status_filter:
        stmt = stmt.where(models.Draft.status == status_filter)
    return [(str(t), c, str(s), str(ft or "")) for (t, c, s, ft) in session.execute(stmt).all()]


def get_agent_logs_for_run(session: Session, run_id: str) -> list[models.AgentLog]:
    stmt = (
        select(models.AgentLog)
        .where(models.AgentLog.run_id == run_id)
        .order_by(models.AgentLog.id.asc())
    )
    return list(session.execute(stmt).scalars().all())


def mark_draft_consumed(
    session: Session,
    draft: models.Draft,
    status: str,
    published_tweet_ids: list[str] | None,
    approval_idempotency_key: str | None,
) -> None:
    draft.status = status
    draft.token_consumed = True
    draft.consumed_at = datetime.now(UTC)
    draft.published_tweet_ids_json = published_tweet_ids
    draft.approval_idempotency_key = approval_idempotency_key


def update_draft_texts(session: Session, draft: models.Draft, new_texts: list[str]) -> None:
    if draft.thread_enabled:
        tweets = [t.strip() for t in new_texts if t.strip()]
        draft.tweets_json = tweets
        draft.final_text = tweets[0] if tweets else ""
    else:
        text = new_texts[0].strip() if new_texts else ""
        draft.final_text = text


def update_draft_policy_report(session: Session, draft: models.Draft, report: PolicyReport) -> None:
    draft.policy_report_json = report.model_dump(mode="json")
    draft.status = "pending" if report.action == "PASS" else "needs_human_attention"
    session.add(
        models.PolicyReport(
            draft_id=draft.id,
            created_at=datetime.now(UTC),
            action=str(report.action),
            risk_level=str(report.risk_level),
            report_json=report.model_dump(mode="json"),
        )
    )


def mark_draft_skipped(session: Session, draft: models.Draft) -> None:
    draft.status = "skipped"
    draft.token_consumed = True
    draft.consumed_at = datetime.now(UTC)


def hash_action_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def issue_action_token(
    session: Session,
    draft: models.Draft,
    action: str,
    ttl_seconds: int,
    one_time: bool,
    created_at: datetime | None = None,
) -> str:
    now = created_at or datetime.now(UTC)
    expires_at = now + timedelta(seconds=ttl_seconds)
    while True:
        raw_token = secrets.token_urlsafe(32)
        token_hash = hash_action_token(raw_token)
        try:
            session.add(
                models.ActionToken(
                    draft_id=draft.id,
                    action=action,
                    token_hash=token_hash,
                    created_at=now,
                    expires_at=expires_at,
                    one_time=one_time,
                    consumed_at=None,
                )
            )
            session.flush()
            return raw_token
        except IntegrityError:
            session.rollback()


def get_action_token(session: Session, action: str, raw_token: str) -> models.ActionToken | None:
    token_hash = hash_action_token(raw_token)
    stmt: Select[tuple[models.ActionToken]] = select(models.ActionToken).where(
        models.ActionToken.action == action,
        models.ActionToken.token_hash == token_hash,
    )
    return session.execute(stmt).scalar_one_or_none()


def resolve_action_token(
    session: Session, action: str, raw_token: str, now: datetime | None = None
) -> tuple[models.Draft | None, models.ActionToken | None, str]:
    now = _as_utc_aware(now or datetime.now(UTC))
    token_row = get_action_token(session, action=action, raw_token=raw_token)
    if token_row is None:
        return None, None, "not_found"
    if now > _as_utc_aware(token_row.expires_at):
        return None, token_row, "expired"
    if token_row.one_time and token_row.consumed_at is not None:
        return None, token_row, "consumed"
    draft = session.get(models.Draft, token_row.draft_id)
    if draft is None:
        return None, token_row, "not_found"
    return draft, token_row, "ok"


def consume_action_token(
    session: Session, token_row: models.ActionToken, consumed_at: datetime | None = None
) -> None:
    if token_row.one_time and token_row.consumed_at is None:
        token_row.consumed_at = consumed_at or datetime.now(UTC)
        session.add(token_row)


def get_publish_attempt(
    session: Session, draft_id: str, attempt: int = 1
) -> models.PublishAttempt | None:
    stmt: Select[tuple[models.PublishAttempt]] = select(models.PublishAttempt).where(
        models.PublishAttempt.draft_id == draft_id,
        models.PublishAttempt.attempt == attempt,
    )
    return session.execute(stmt).scalar_one_or_none()


def try_start_publish_attempt(
    session: Session,
    draft: models.Draft,
    attempt: int,
    owner: str | None,
    created_at: datetime | None = None,
) -> tuple[bool, models.PublishAttempt | None]:
    publish_attempt = models.PublishAttempt(
        draft_id=draft.id,
        attempt=attempt,
        owner=owner,
        status="started",
        created_at=created_at or datetime.now(UTC),
        completed_at=None,
        last_error=None,
    )
    try:
        session.add(publish_attempt)
        session.flush()
        return True, publish_attempt
    except IntegrityError:
        session.rollback()
        return False, get_publish_attempt(session, draft.id, attempt=attempt)


def mark_publish_attempt_completed(
    session: Session,
    publish_attempt: models.PublishAttempt,
    completed_at: datetime | None = None,
) -> None:
    publish_attempt.status = "completed"
    publish_attempt.completed_at = completed_at or datetime.now(UTC)
    publish_attempt.last_error = None
    session.add(publish_attempt)


def mark_publish_attempt_failed(
    session: Session,
    publish_attempt: models.PublishAttempt,
    error: str,
    completed_at: datetime | None = None,
) -> None:
    publish_attempt.status = "failed"
    publish_attempt.completed_at = completed_at or datetime.now(UTC)
    publish_attempt.last_error = error[:500]
    session.add(publish_attempt)


def insert_post_idempotent(
    session: Session,
    draft: models.Draft,
    position: int,
    tweet_id: str,
    content: str,
    publish_idempotency_key: str,
    posted_at: datetime | None = None,
) -> None:
    try:
        session.add(
            models.Post(
                draft_id=draft.id,
                position=position,
                tweet_id=tweet_id,
                content=content,
                posted_at=posted_at or datetime.now(UTC),
                publish_idempotency_key=publish_idempotency_key,
            )
        )
        session.flush()
    except IntegrityError:
        session.rollback()


def get_existing_thread_posts(session: Session, draft: models.Draft) -> dict[int, str]:
    stmt = select(models.Post.position, models.Post.tweet_id).where(
        models.Post.draft_id == draft.id
    )
    rows = session.execute(stmt).all()
    return {int(pos): str(tid) for (pos, tid) in rows}


def get_latest_publish_attempt(session: Session, draft_id: str) -> models.PublishAttempt | None:
    stmt: Select[tuple[models.PublishAttempt]] = (
        select(models.PublishAttempt)
        .where(models.PublishAttempt.draft_id == draft_id)
        .order_by(models.PublishAttempt.attempt.desc())
        .limit(1)
    )
    return session.execute(stmt).scalar_one_or_none()


def get_recent_posts(session: Session, days: int = 14, limit: int = 200) -> list[str]:
    cutoff = datetime.now(UTC) - timedelta(days=days)
    stmt = (
        select(models.Post.content)
        .where(models.Post.posted_at > cutoff)
        .order_by(models.Post.posted_at.desc())
        .limit(limit)
    )
    return [str(r[0]) for r in session.execute(stmt).all() if r[0]]


def get_posts_in_window(session: Session, start: datetime, end: datetime) -> list[str]:
    stmt = (
        select(models.Post.content)
        .where(models.Post.posted_at >= start, models.Post.posted_at < end)
        .order_by(models.Post.posted_at.desc())
    )
    return [str(r[0]) for r in session.execute(stmt).all() if r[0]]


def save_style_profile(
    session: Session, profile: StyleProfile, created_at: datetime | None = None
) -> None:
    session.add(
        models.StyleProfile(
            created_at=created_at or datetime.now(UTC),
            profile_json=profile.model_dump(mode="json"),
        )
    )


def get_latest_style_profile(session: Session) -> StyleProfile | None:
    stmt = (
        select(models.StyleProfile.profile_json)
        .order_by(models.StyleProfile.created_at.desc())
        .limit(1)
    )
    row = session.execute(stmt).first()
    if not row or not row[0]:
        return None
    try:
        return StyleProfile(**row[0])
    except Exception:
        return None


def save_weekly_report(session: Session, report: WeeklyReport) -> None:
    session.add(
        models.WeeklyReport(
            week_start=report.week_start,
            week_end=report.week_end,
            created_at=datetime.now(UTC),
            report_json=report.model_dump(mode="json"),
        )
    )


def runs_grouped_by_status(session: Session) -> list[tuple[str, int]]:
    stmt = select(models.Run.status, func.count(models.Run.run_id)).group_by(models.Run.status)
    return [(str(status), int(count)) for status, count in session.execute(stmt).all()]


def drafts_count(session: Session) -> int:
    return int(session.execute(select(func.count(models.Draft.id))).scalar_one())


def posts_count(session: Session) -> int:
    return int(session.execute(select(func.count(models.Post.id))).scalar_one())


def avg_run_duration_ms(session: Session) -> float:
    stmt = select(func.avg(models.Run.duration_ms)).where(models.Run.duration_ms.is_not(None))
    value = session.execute(stmt).scalar_one()
    return float(value or 0.0)


def hash_password(raw_password: str) -> str:
    hashed = bcrypt.hashpw(raw_password.encode("utf-8"), bcrypt.gensalt(rounds=12))
    return hashed.decode("utf-8")


def verify_password(raw_password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(raw_password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


def get_user_by_username(session: Session, username: str) -> models.User | None:
    stmt: Select[tuple[models.User]] = select(models.User).where(models.User.username == username)
    return session.execute(stmt).scalar_one_or_none()


def get_user(session: Session, user_id: str) -> models.User | None:
    return session.get(models.User, user_id)


def ensure_user(
    session: Session,
    *,
    username: str,
    raw_password: str,
    role: str,
    created_at: datetime | None = None,
) -> models.User:
    existing = get_user_by_username(session, username)
    if existing is not None:
        return existing
    now = created_at or datetime.now(UTC)
    user = models.User(
        id=str(uuid.uuid4()),
        username=username,
        password_hash=hash_password(raw_password),
        role=role,
        created_at=now,
    )
    session.add(user)
    session.flush()
    return user


def create_user_session(
    session: Session,
    *,
    session_id: str,
    user_id: str,
    csrf_token: str,
    created_at: datetime,
    expires_at: datetime,
    ip_address: str | None,
    user_agent: str | None,
) -> None:
    session.add(
        models.UserSession(
            id=session_id,
            user_id=user_id,
            csrf_token=csrf_token,
            created_at=created_at,
            expires_at=expires_at,
            last_seen_at=created_at,
            ip_address=ip_address,
            user_agent=user_agent[:200] if user_agent else None,
        )
    )


def get_user_session(
    session: Session, session_id: str, now: datetime | None = None
) -> models.UserSession | None:
    now = _as_utc_aware(now or datetime.now(UTC))
    row = session.get(models.UserSession, session_id)
    if row is None:
        return None
    if now > _as_utc_aware(row.expires_at):
        session.delete(row)
        session.flush()
        return None
    row.last_seen_at = now
    session.add(row)
    return row


def delete_user_session(session: Session, session_id: str) -> None:
    row = session.get(models.UserSession, session_id)
    if row is not None:
        session.delete(row)


def get_app_config(session: Session, key: str) -> dict | None:
    row = session.get(models.AppConfig, key)
    if row is None:
        return None
    return dict(row.value_json or {})


def set_app_config(session: Session, key: str, value: dict) -> None:
    now = datetime.now(UTC)
    row = session.get(models.AppConfig, key)
    if row is None:
        session.add(models.AppConfig(key=key, value_json=value, updated_at=now))
        return
    row.value_json = value
    row.updated_at = now
    session.add(row)


def add_audit_log(
    session: Session,
    *,
    user_id: str,
    action: str,
    draft_id: str | None,
    details: dict,
    ip_address: str | None,
    created_at: datetime | None = None,
) -> None:
    session.add(
        models.AuditLog(
            user_id=user_id,
            action=action[:50],
            draft_id=draft_id,
            created_at=created_at or datetime.now(UTC),
            ip_address=ip_address,
            details_json=details,
        )
    )
