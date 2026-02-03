from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

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


def get_run(session: Session, run_id: str) -> models.Run | None:
    return session.get(models.Run, run_id)


def create_run(session: Session, run_id: str, source: str, created_at: datetime) -> None:
    if session.get(models.Run, run_id) is not None:
        return
    session.add(models.Run(run_id=run_id, source=source, status="running", created_at=created_at))


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
    token: str,
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
    existing = get_draft_by_token(session, token)
    if existing is not None:
        return existing
    draft_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"draft_id:{token}"))
    thread_plan_json = thread_plan.model_dump(mode="json") if thread_plan else None
    tweets_json = edited_draft.final_tweets if edited_draft.mode == "thread" else None
    final_text = edited_draft.final_text or (tweets_json[0] if tweets_json else "")
    d = models.Draft(
        id=draft_id,
        token=token,
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


def get_draft_by_token(session: Session, token: str) -> models.Draft | None:
    stmt: Select[tuple[models.Draft]] = select(models.Draft).where(models.Draft.token == token)
    return session.execute(stmt).scalar_one_or_none()


def list_drafts(
    session: Session, since: datetime, status_filter: str | None, limit: int = 200
) -> list[tuple[str, datetime, str, str]]:
    stmt = (
        select(
            models.Draft.token,
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
