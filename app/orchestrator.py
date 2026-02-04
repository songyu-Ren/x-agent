import json
import logging
import os
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete

from app.agents.collector import CollectorAgent
from app.agents.critic import CriticAgent
from app.agents.curator import CuratorAgent
from app.agents.notifier import NotifierAgent
from app.agents.policy import PolicyAgent
from app.agents.publisher import PublisherAgent
from app.agents.style import StyleAgent
from app.agents.thread_planner import ThreadPlannerAgent
from app.agents.weekly_analyst import WeeklyAnalystAgent
from app.agents.writer import WriterAgent
from app.config import settings
from app.models import (
    AgentLog,
    ApprovedDraftRecord,
    DraftCandidates,
    EditedDraft,
    Materials,
    PolicyReport,
    PublishRequest,
    RunState,
    StyleProfile,
    ThreadPlan,
    TopicPlan,
    WeeklyReport,
)
from app.services.email_service import send_email_html
from app.services.whatsapp_service import send_whatsapp
from infrastructure.db import models
from infrastructure.db import repositories as db
from infrastructure.db.session import get_sessionmaker

logger = logging.getLogger(__name__)


class Orchestrator:
    def __init__(self) -> None:
        self.collector = CollectorAgent()
        self.curator = CuratorAgent()
        self.style_agent = StyleAgent()
        self.thread_planner = ThreadPlannerAgent()
        self.writer = WriterAgent()
        self.critic = CriticAgent()
        self.policy = PolicyAgent()
        self.notifier = NotifierAgent()
        self.publisher = PublisherAgent()
        self.weekly_analyst = WeeklyAnalystAgent()

    def start_run(self, source: str = "scheduler", run_id: str | None = None) -> str:
        run_id = run_id or str(uuid.uuid4())
        started_at = datetime.now(UTC)
        run_state = RunState(run_id=run_id, created_at=started_at, source=source)
        with get_sessionmaker()() as session:
            db.create_run(session, run_id=run_id, source=source, created_at=started_at)
            session.commit()

        logs: list[AgentLog] = []
        try:
            self._execute_workflow(run_state, logs)
            self._finalize_run(run_id, "completed", started_at, None, logs)
        except Exception as e:
            self._finalize_run(run_id, "failed", started_at, str(e), logs)
        return run_id

    def update_style_profile(self) -> None:
        posts = self._get_recent_posts(limit=int(getattr(settings, "STYLE_INPUT_POSTS", 30) or 30))
        devlog_excerpt = ""
        try:
            if os.path.exists(settings.DEVLOG_PATH):
                with open(settings.DEVLOG_PATH, encoding="utf-8") as f:
                    devlog_excerpt = f.read()[-2000:]
        except Exception:
            devlog_excerpt = ""

        profile, log = self.style_agent.execute((posts, devlog_excerpt))
        self._save_style_profile(profile)
        self._write_style_cache(profile)

    def generate_weekly_report(self) -> WeeklyReport:
        now = datetime.now(UTC)
        week_end = now
        week_start = now - timedelta(days=7)
        posts = self._get_posts_in_window(week_start, week_end)
        report = self.weekly_analyst.run((week_start, week_end, posts))
        self._save_weekly_report(report)
        self._send_weekly_report(report)
        return report

    def _send_weekly_report(self, report: WeeklyReport) -> None:
        subject = f"Weekly X Report: {report.week_start.date()} - {report.week_end.date()}"
        html = f"""
        <h2>Weekly Report</h2>
        <p><b>Window:</b> {report.week_start.isoformat()} → {report.week_end.isoformat()}</p>
        <h3>Top Buckets</h3>
        <ul>{''.join([f'<li>{b}</li>' for b in report.top_topic_buckets])}</ul>
        <h3>Recommendations</h3>
        <ul>{''.join([f'<li>{r}</li>' for r in report.recommendations])}</ul>
        <h3>Next Week Topics</h3>
        <ul>{''.join([f'<li>{t}</li>' for t in report.next_week_topics])}</ul>
        """
        send_email_html(subject, html)
        if settings.ENABLE_WHATSAPP:
            body = "Weekly report is ready. Check email for details."
            send_whatsapp(body)

    def approve_draft(self, token: str) -> tuple[int, str]:
        with get_sessionmaker()() as session:
            draft, token_row, token_status = db.resolve_action_token(
                session=session, action="approve", raw_token=token
            )
            if token_status == "not_found":
                return 404, "Token not found"
            if token_status == "expired":
                return 410, "Token expired"
            if token_status == "consumed":
                return 200, "Already processed"
            if draft is None or token_row is None:
                return 404, "Token not found"

            if draft.token_consumed:
                return 200, f"Already processed: {draft.status}"

            if _is_expired(draft.expires_at):
                return 410, "Token expired"

            if draft.status in {"posted", "dry_run_posted", "skipped", "error"}:
                return 200, f"Already {draft.status}"

            materials = Materials(**draft.materials_json)
            style = StyleProfile(**draft.style_profile_json)
            recent_posts = db.get_recent_posts(session, days=14)

            edited_draft = EditedDraft(**draft.edited_draft_json)
            edited_draft.final_text = str(draft.final_text or edited_draft.final_text or "")
            if draft.thread_enabled and draft.tweets_json:
                edited_draft.final_tweets = [str(t) for t in draft.tweets_json if t]

        report, _ = self.policy.execute((edited_draft, materials, recent_posts, style))
        if report.action != "PASS":
            return 403, "Policy check failed"

        publish_owner = str(uuid.uuid4())
        draft_id: str
        with get_sessionmaker()() as session:
            draft, token_row, token_status = db.resolve_action_token(
                session=session, action="approve", raw_token=token
            )
            if token_status == "not_found":
                return 404, "Token not found"
            if token_status == "expired":
                return 410, "Token expired"
            if token_status == "consumed":
                return 200, "Already processed"
            if draft is None or token_row is None:
                return 404, "Token not found"
            if draft.token_consumed:
                return 200, f"Already processed: {draft.status}"
            if _is_expired(draft.expires_at):
                return 410, "Token expired"

            draft_id = draft.id
            started, attempt_row = db.try_start_publish_attempt(
                session=session, draft=draft, attempt=1, owner=publish_owner
            )
            if not started:
                if attempt_row is None:
                    return 409, "Publish already started"
                if attempt_row.status == "completed":
                    return 200, f"Already processed: {draft.status}"
                if attempt_row.status == "failed":
                    return 409, "Previous publish attempt failed; use resume action"
                return 200, "Publish already in progress"

            draft.status = "publishing"
            db.consume_action_token(session, token_row)
            session.commit()

        if edited_draft.mode == "thread":
            tweets = list(
                edited_draft.final_tweets
                or ([edited_draft.final_text] if edited_draft.final_text else [])
            )
        else:
            tweets = [edited_draft.final_text or ""]
        tweets = [t for t in tweets if t]

        publish_req = PublishRequest(
            draft_id=draft_id, tweets=tweets, dry_run=bool(settings.DRY_RUN), reply_chain=True
        )

        try:
            result = self.publisher.run(publish_req)
            tweet_ids = result.tweet_ids
            new_status = "dry_run_posted" if settings.DRY_RUN else "posted"

            with get_sessionmaker()() as session:
                draft_row = db.get_draft(session, draft_id)
                if draft_row is None:
                    return 404, "Draft not found"
                attempt_row = db.get_publish_attempt(session, draft_id, attempt=1)
                db.mark_draft_consumed(
                    session=session,
                    draft=draft_row,
                    status=new_status,
                    published_tweet_ids=tweet_ids,
                    approval_idempotency_key=f"approve:{draft_id}",
                )
                if attempt_row is not None:
                    db.mark_publish_attempt_completed(session, attempt_row)
                session.commit()
            return 200, f"Published: {tweet_ids}"
        except Exception as e:
            with get_sessionmaker()() as session:
                draft_row = db.get_draft(session, draft_id)
                if draft_row is not None:
                    attempt_row = db.get_publish_attempt(session, draft_id, attempt=1)
                    draft_row.status = "error"
                    draft_row.last_error = str(e)[:500]
                    if attempt_row is not None:
                        db.mark_publish_attempt_failed(session, attempt_row, error=str(e))
                    session.commit()
            return 500, "Publish failed"

    def save_edit(self, token: str, new_texts: list[str]) -> tuple[int, PolicyReport]:
        with get_sessionmaker()() as session:
            draft, _, token_status = db.resolve_action_token(
                session=session, action="edit", raw_token=token
            )
            if token_status == "not_found" or draft is None:
                raise RuntimeError("Not found")
            if token_status == "expired":
                raise RuntimeError("Expired")
            if _is_expired(draft.expires_at):
                raise RuntimeError("Expired")
            if draft.token_consumed:
                raise RuntimeError("Token consumed")

            materials = Materials(**draft.materials_json)
            style = StyleProfile(**draft.style_profile_json)
            recent_posts = db.get_recent_posts(session, days=14)
            edited = EditedDraft(**draft.edited_draft_json)

            db.update_draft_texts(session, draft, new_texts)
            edited.final_text = draft.final_text or ""
            edited.final_tweets = list(draft.tweets_json or []) if draft.thread_enabled else None
            draft.edited_draft_json = edited.model_dump(mode="json")
            session.commit()

        report, _ = self.policy.execute((edited, materials, recent_posts, style))
        self._update_policy_report(draft.id, report)
        return 200, report

    def save_edit_by_id(self, draft_id: str, new_texts: list[str]) -> tuple[int, PolicyReport]:
        with get_sessionmaker()() as session:
            draft = db.get_draft(session, draft_id)
            if draft is None:
                raise RuntimeError("Not found")
            if _is_expired(draft.expires_at):
                raise RuntimeError("Expired")
            if draft.token_consumed:
                raise RuntimeError("Token consumed")

            materials = Materials(**draft.materials_json)
            style = StyleProfile(**draft.style_profile_json)
            recent_posts = db.get_recent_posts(session, days=14)
            edited = EditedDraft(**draft.edited_draft_json)

            db.update_draft_texts(session, draft, new_texts)
            edited.final_text = draft.final_text or ""
            edited.final_tweets = list(draft.tweets_json or []) if draft.thread_enabled else None
            draft.edited_draft_json = edited.model_dump(mode="json")
            session.commit()

        report, _ = self.policy.execute((edited, materials, recent_posts, style))
        self._update_policy_report(draft_id, report)
        return 200, report

    def regenerate(self, token: str) -> tuple[int, str]:
        with get_sessionmaker()() as session:
            draft, _, token_status = db.resolve_action_token(
                session=session, action="regenerate", raw_token=token
            )
            if token_status == "not_found" or draft is None:
                return 404, "Not found"
            if token_status == "expired":
                return 410, "Expired"
            if draft.token_consumed:
                return 409, "Already consumed"

            materials = Materials(**draft.materials_json)
            topic_plan = TopicPlan(**draft.topic_plan_json)
            style = StyleProfile(**draft.style_profile_json)
            thread_plan = (
                ThreadPlan(**draft.thread_plan_json)
                if draft.thread_plan_json
                else ThreadPlan(enabled=False, tweets_count=1)
            )
            recent_posts = db.get_recent_posts(session, days=14)

        candidates, _ = self.writer.execute((topic_plan, thread_plan, style, materials))
        edited, _ = self.critic.execute((candidates, materials, style, thread_plan))
        report, _ = self.policy.execute((edited, materials, recent_posts, style))

        self._update_draft_generation(draft.id, candidates, edited, report, style, thread_plan)
        return 200, "Regenerated"

    def regenerate_by_id(self, draft_id: str) -> tuple[int, str]:
        with get_sessionmaker()() as session:
            draft = db.get_draft(session, draft_id)
            if draft is None:
                return 404, "Not found"
            if _is_expired(draft.expires_at):
                return 410, "Expired"
            if draft.token_consumed:
                return 409, "Already consumed"

            materials = Materials(**draft.materials_json)
            topic_plan = TopicPlan(**draft.topic_plan_json)
            style = StyleProfile(**draft.style_profile_json)
            thread_plan = (
                ThreadPlan(**draft.thread_plan_json)
                if draft.thread_plan_json
                else ThreadPlan(enabled=False, tweets_count=1)
            )
            recent_posts = db.get_recent_posts(session, days=14)

        candidates, _ = self.writer.execute((topic_plan, thread_plan, style, materials))
        edited, _ = self.critic.execute((candidates, materials, style, thread_plan))
        report, _ = self.policy.execute((edited, materials, recent_posts, style))

        self._update_draft_generation(draft_id, candidates, edited, report, style, thread_plan)
        return 200, "Regenerated"

    def skip_draft(self, token: str) -> tuple[int, str]:
        with get_sessionmaker()() as session:
            draft, token_row, token_status = db.resolve_action_token(
                session=session, action="skip", raw_token=token
            )
            if token_status == "not_found":
                return 404, "Not found"
            if token_status == "expired":
                return 410, "Expired"
            if token_status == "consumed":
                return 200, "Already skipped"
            if draft is None or token_row is None:
                return 404, "Not found"
            if _is_expired(draft.expires_at):
                return 410, "Expired"
            if draft.token_consumed:
                return 409, "Token consumed"
            db.mark_draft_skipped(session, draft)
            db.consume_action_token(session, token_row)
            session.commit()
        return 200, "Skipped"

    def _execute_workflow(self, run_state: RunState, logs: list[AgentLog]) -> None:
        materials, log = self.collector.execute(run_state)
        logs.append(log)

        recent_posts = self._get_recent_posts(days=14)
        topic_plan, log = self.curator.execute((materials, recent_posts))
        logs.append(log)

        style_profile = self._get_style_profile()
        thread_plan, log = self.thread_planner.execute((topic_plan, materials, style_profile))
        logs.append(log)

        max_rewrites = int(getattr(settings, "REWRITE_MAX", 1) or 1)
        rewrites = 0

        candidates: DraftCandidates
        edited: EditedDraft
        report: PolicyReport

        while True:
            candidates, log = self.writer.execute(
                (topic_plan, thread_plan, style_profile, materials)
            )
            logs.append(log)

            edited, log = self.critic.execute((candidates, materials, style_profile, thread_plan))
            logs.append(log)

            report, log = self.policy.execute((edited, materials, recent_posts, style_profile))
            logs.append(log)

            if report.action == "PASS":
                break
            if report.action == "REWRITE" and rewrites < max_rewrites:
                rewrites += 1
                continue
            break

        token = self._create_draft_record(
            run_state.run_id,
            materials,
            topic_plan,
            style_profile,
            thread_plan,
            candidates,
            edited,
            report,
        )
        draft_id, view_token, edit_token, approve_token, skip_token = token
        status = "pending" if report.action == "PASS" else "needs_human_attention"
        self._update_draft_status(draft_id, status)

        record = ApprovedDraftRecord(
            draft_id=draft_id,
            approve_token=approve_token,
            edit_token=edit_token,
            skip_token=skip_token,
            view_token=view_token,
            mode=edited.mode,
            text=edited.final_text,
            tweets=edited.final_tweets,
            policy_report=report,
        )

        _, log = self.notifier.execute(record)
        logs.append(log)

    def _finalize_run(
        self,
        run_id: str,
        status: str,
        started_at: datetime,
        error: str | None,
        logs: list[AgentLog],
    ) -> None:
        finished = datetime.now(UTC)
        duration_ms = int((finished - started_at).total_seconds() * 1000)

        with get_sessionmaker()() as session:
            db.update_run_status(
                session=session,
                run_id=run_id,
                status=status,
                finished_at=finished,
                duration_ms=duration_ms,
                last_error=(error[:500] if error else None),
            )
            session.execute(delete(models.AgentLog).where(models.AgentLog.run_id == run_id))
            for log_item in logs:
                db.add_agent_log(session, run_id=run_id, log=log_item)
            session.commit()

    def _create_draft_record(
        self,
        run_id: str,
        materials: Materials,
        plan: TopicPlan,
        style: StyleProfile,
        thread_plan: ThreadPlan,
        candidates: DraftCandidates,
        edited: EditedDraft,
        report: PolicyReport,
    ) -> tuple[str, str, str, str, str]:
        draft_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"draft_id:{run_id}"))
        now = datetime.now(UTC)
        ttl_hours = int(getattr(settings, "TOKEN_TTL_HOURS", 36) or 36)
        expires = now + timedelta(hours=ttl_hours)
        status = "pending" if report.action == "PASS" else "needs_human_attention"
        with get_sessionmaker()() as session:
            existing = db.get_draft(session, draft_id)
            draft = existing
            if draft is None:
                draft = db.create_draft(
                    session=session,
                    run_id=run_id,
                    draft_id=draft_id,
                    token_hash=secrets.token_hex(32),
                    created_at=now,
                    expires_at=expires,
                    status=status,
                    materials=materials,
                    topic_plan=plan,
                    style_profile=style,
                    thread_plan=thread_plan,
                    candidates=candidates,
                    edited_draft=edited,
                    policy_report=report,
                )

            ttl_seconds = ttl_hours * 3600
            view_token = db.issue_action_token(
                session=session, draft=draft, action="view", ttl_seconds=ttl_seconds, one_time=False
            )
            edit_token = db.issue_action_token(
                session=session, draft=draft, action="edit", ttl_seconds=ttl_seconds, one_time=False
            )
            approve_token = db.issue_action_token(
                session=session,
                draft=draft,
                action="approve",
                ttl_seconds=ttl_seconds,
                one_time=True,
            )
            skip_token = db.issue_action_token(
                session=session, draft=draft, action="skip", ttl_seconds=ttl_seconds, one_time=True
            )
            _ = db.issue_action_token(
                session=session,
                draft=draft,
                action="regenerate",
                ttl_seconds=ttl_seconds,
                one_time=False,
            )
            session.commit()
        return draft_id, view_token, edit_token, approve_token, skip_token

    def _update_draft_status(self, draft_id: str, status: str) -> None:
        with get_sessionmaker()() as session:
            draft = db.get_draft(session, draft_id)
            if draft is None:
                return
            draft.status = status
            session.commit()

    def _update_policy_report(self, draft_id: str, report: PolicyReport) -> None:
        with get_sessionmaker()() as session:
            draft = db.get_draft(session, draft_id)
            if draft is None:
                return
            db.update_draft_policy_report(session, draft, report)
            session.commit()

    def _update_draft_generation(
        self,
        draft_id: str,
        candidates: DraftCandidates,
        edited: EditedDraft,
        report: PolicyReport,
        style: StyleProfile,
        thread_plan: ThreadPlan,
    ) -> None:
        with get_sessionmaker()() as session:
            draft = db.get_draft(session, draft_id)
            if draft is None:
                return

            draft.candidates_json = candidates.model_dump(mode="json")
            draft.edited_draft_json = edited.model_dump(mode="json")
            draft.style_profile_json = style.model_dump(mode="json")
            draft.thread_plan_json = thread_plan.model_dump(mode="json") if thread_plan else None
            if draft.thread_enabled and edited.final_tweets:
                draft.tweets_json = [t for t in edited.final_tweets if t]
                draft.final_text = draft.tweets_json[0] if draft.tweets_json else ""
            else:
                draft.tweets_json = None
                draft.final_text = edited.final_text or ""

            db.update_draft_policy_report(session, draft, report)
            session.commit()

    def _get_recent_posts(self, days: int = 14, limit: int = 200) -> list[str]:
        with get_sessionmaker()() as session:
            return db.get_recent_posts(session, days=days, limit=limit)

    def _get_posts_in_window(self, start: datetime, end: datetime) -> list[str]:
        with get_sessionmaker()() as session:
            return db.get_posts_in_window(session, start=start, end=end)

    def _save_style_profile(self, profile: StyleProfile) -> None:
        with get_sessionmaker()() as session:
            db.save_style_profile(session, profile)
            session.commit()

    def _write_style_cache(self, profile: StyleProfile) -> None:
        try:
            with open("style_profile.json", "w", encoding="utf-8") as f:
                f.write(profile.model_dump_json())
        except Exception:
            return

    def _get_style_profile(self) -> StyleProfile:
        with get_sessionmaker()() as session:
            profile = db.get_latest_style_profile(session)
            if profile is not None:
                return profile
        try:
            if os.path.exists("style_profile.json"):
                with open("style_profile.json", encoding="utf-8") as f:
                    return StyleProfile(**json.loads(f.read()))
        except Exception:
            pass
        return StyleProfile(
            preferred_openers=["Today:", "Quick note:"],
            forbidden_phrases=["game changer", "revolutionary"],
            sentence_length_preference="short",
            tone_rules=["No marketing", "No emojis", "No hashtags"],
            formatting_rules=["Prefer 1-2 short lines"],
        )

    def _get_style_profile_from_row(self, row_dict: dict) -> StyleProfile:
        try:
            if row_dict.get("style_profile_json"):
                return StyleProfile(**json.loads(row_dict["style_profile_json"]))
        except Exception:
            pass
        return self._get_style_profile()

    def _save_weekly_report(self, report: WeeklyReport) -> None:
        with get_sessionmaker()() as session:
            db.save_weekly_report(session, report)
            session.commit()


def _is_expired(expires_at_value) -> bool:
    try:
        if isinstance(expires_at_value, str):
            expires_at = datetime.fromisoformat(expires_at_value)
        else:
            expires_at = expires_at_value
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return datetime.now(UTC) > expires_at
    except Exception:
        return False


orchestrator = Orchestrator()
