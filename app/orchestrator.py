import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

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
from app.database import get_connection
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

logger = logging.getLogger(__name__)


class Orchestrator:
    def __init__(self):
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

    def start_run(self, source: str = "scheduler") -> str:
        run_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc)
        run_state = RunState(run_id=run_id, created_at=started_at, source=source)
        self._save_run(run_state)

        logs: list[AgentLog] = []
        try:
            self._execute_workflow(run_state, logs)
            self._update_run_status(run_id, "completed", started_at, None)
        except Exception as e:
            self._update_run_status(run_id, "failed", started_at, str(e))
        return run_id

    def update_style_profile(self) -> None:
        posts = self._get_recent_posts(limit=int(getattr(settings, "STYLE_INPUT_POSTS", 30) or 30))
        devlog_excerpt = ""
        try:
            if os.path.exists(settings.DEVLOG_PATH):
                with open(settings.DEVLOG_PATH, "r", encoding="utf-8") as f:
                    devlog_excerpt = f.read()[-2000:]
        except Exception:
            devlog_excerpt = ""

        profile, log = self.style_agent.execute((posts, devlog_excerpt))
        self._save_style_profile(profile)
        self._write_style_cache(profile)

    def generate_weekly_report(self) -> WeeklyReport:
        now = datetime.now(timezone.utc)
        week_end = now
        week_start = now - timedelta(days=7)
        posts = self._get_posts_in_window(week_start, week_end)
        report, _ = self.weekly_analyst.execute((week_start, week_end, posts))
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
        conn = get_connection()
        row = conn.execute("SELECT * FROM drafts WHERE token = ?", (token,)).fetchone()
        if not row:
            conn.close()
            return 404, "Token not found"

        if row["token_consumed"] == 1:
            status_val = row["status"]
            conn.close()
            return 200, f"Already processed: {status_val}"

        if _is_expired(row["expires_at"]):
            conn.close()
            return 410, "Token expired"

        if row["status"] in ["posted", "dry_run_posted", "skipped", "error"]:
            conn.close()
            return 200, f"Already {row['status']}"

        materials = Materials(**json.loads(row["materials_json"]))
        style = self._get_style_profile_from_row(row)
        recent_posts = self._get_recent_posts(days=14)

        edited_draft = EditedDraft(**json.loads(row["edited_draft_json"]))
        edited_draft.final_text = row["final_text"]
        if "tweets_json" in row.keys() and row["tweets_json"]:
            try:
                edited_draft.final_tweets = json.loads(row["tweets_json"])
            except Exception:
                edited_draft.final_tweets = None

        report, _ = self.policy.execute((edited_draft, materials, recent_posts, style))
        if report.action != "PASS":
            conn.close()
            return 403, "Policy check failed"

        tweets = edited_draft.final_tweets if edited_draft.mode == "thread" else [edited_draft.final_text or ""]
        tweets = [t for t in tweets if t]

        publish_req = PublishRequest(
            token=token,
            tweets=tweets,
            dry_run=bool(settings.DRY_RUN),
            reply_chain=True,
        )

        try:
            result = self.publisher.run(publish_req)
            tweet_ids = result.tweet_ids
            new_status = "dry_run_posted" if settings.DRY_RUN else "posted"
            first_id = tweet_ids[0] if tweet_ids else None

            conn.execute(
                """
                UPDATE drafts
                SET status=?, tweet_id=?, token_consumed=1, consumed_at=datetime('now'), published_tweet_ids_json=?
                WHERE token=?
                """,
                (new_status, first_id, json.dumps(tweet_ids), token),
            )

            if not settings.DRY_RUN:
                for tid, text in zip(tweet_ids, tweets):
                    conn.execute(
                        "INSERT OR IGNORE INTO posts (tweet_id, content, posted_at) VALUES (?, ?, datetime('now'))",
                        (tid, text),
                    )

            conn.commit()
            conn.close()
            return 200, f"Published: {tweet_ids}"
        except Exception as e:
            conn.execute(
                "UPDATE drafts SET status='error', last_error=? WHERE token=?",
                (str(e)[:500], token),
            )
            conn.commit()
            conn.close()
            return 500, "Publish failed"

    def save_edit(self, token: str, new_texts: list[str]) -> tuple[int, PolicyReport]:
        conn = get_connection()
        row = conn.execute("SELECT * FROM drafts WHERE token = ?", (token,)).fetchone()
        if not row:
            conn.close()
            raise RuntimeError("Not found")
        if _is_expired(row["expires_at"]):
            conn.close()
            raise RuntimeError("Expired")
        if row["token_consumed"] == 1:
            conn.close()
            raise RuntimeError("Token consumed")

        materials = Materials(**json.loads(row["materials_json"]))
        style = self._get_style_profile_from_row(row)
        recent_posts = self._get_recent_posts(days=14)

        edited = EditedDraft(**json.loads(row["edited_draft_json"]))

        if edited.mode == "thread":
            tweets = [t.strip() for t in new_texts if t.strip()]
            conn.execute(
                "UPDATE drafts SET tweets_json=?, final_text=? WHERE token=?",
                (json.dumps(tweets), tweets[0] if tweets else "", token),
            )
            edited.final_tweets = tweets
            edited.final_text = tweets[0] if tweets else ""
        else:
            text = new_texts[0].strip() if new_texts else ""
            conn.execute("UPDATE drafts SET final_text=? WHERE token=?", (text, token))
            edited.final_text = text

        conn.commit()
        conn.close()

        report, _ = self.policy.execute((edited, materials, recent_posts, style))
        self._update_policy_report(token, report)
        return 200, report

    def regenerate(self, token: str) -> tuple[int, str]:
        conn = get_connection()
        row = conn.execute("SELECT * FROM drafts WHERE token = ?", (token,)).fetchone()
        if not row:
            conn.close()
            return 404, "Not found"
        if row["token_consumed"] == 1:
            conn.close()
            return 409, "Already consumed"

        materials = Materials(**json.loads(row["materials_json"]))
        topic_plan = TopicPlan(**json.loads(row["topic_plan_json"]))
        style = self._get_style_profile_from_row(row)
        thread_plan = (
            ThreadPlan(**json.loads(row["thread_plan_json"]))
            if "thread_plan_json" in row.keys() and row["thread_plan_json"]
            else ThreadPlan(enabled=False, tweets_count=1)
        )
        recent_posts = self._get_recent_posts(days=14)

        candidates, _ = self.writer.execute((topic_plan, thread_plan, style, materials))
        edited, _ = self.critic.execute((candidates, materials, style, thread_plan))
        report, _ = self.policy.execute((edited, materials, recent_posts, style))

        self._update_draft_generation(token, candidates, edited, report, style, thread_plan)
        conn.close()
        return 200, "Regenerated"

    def skip_draft(self, token: str) -> tuple[int, str]:
        conn = get_connection()
        row = conn.execute("SELECT * FROM drafts WHERE token = ?", (token,)).fetchone()
        if not row:
            conn.close()
            return 404, "Not found"
        if _is_expired(row["expires_at"]):
            conn.close()
            return 410, "Expired"
        if row["token_consumed"] == 1:
            conn.close()
            return 409, "Token consumed"
        conn.execute("UPDATE drafts SET status='skipped' WHERE token=?", (token,))
        conn.commit()
        conn.close()
        return 200, "Skipped"

    def _execute_workflow(self, run_state: RunState, logs: list[AgentLog]) -> None:
        materials, log = self.collector.execute(run_state)
        logs.append(log)
        self._save_logs(run_state.run_id, logs)

        recent_posts = self._get_recent_posts(days=14)
        topic_plan, log = self.curator.execute((materials, recent_posts))
        logs.append(log)
        self._save_logs(run_state.run_id, logs)

        style_profile = self._get_style_profile()
        thread_plan, log = self.thread_planner.execute((topic_plan, materials, style_profile))
        logs.append(log)
        self._save_logs(run_state.run_id, logs)

        max_rewrites = int(getattr(settings, "REWRITE_MAX", 1) or 1)
        rewrites = 0

        candidates: DraftCandidates
        edited: EditedDraft
        report: PolicyReport

        while True:
            candidates, log = self.writer.execute((topic_plan, thread_plan, style_profile, materials))
            logs.append(log)
            self._save_logs(run_state.run_id, logs)

            edited, log = self.critic.execute((candidates, materials, style_profile, thread_plan))
            logs.append(log)
            self._save_logs(run_state.run_id, logs)

            report, log = self.policy.execute((edited, materials, recent_posts, style_profile))
            logs.append(log)
            self._save_logs(run_state.run_id, logs)

            if report.action == "PASS":
                break
            if report.action == "REWRITE" and rewrites < max_rewrites:
                rewrites += 1
                continue
            break

        token = self._create_draft_record(run_state.run_id, materials, topic_plan, style_profile, thread_plan, candidates, edited, report)
        status = "pending" if report.action == "PASS" else "needs_human_attention"
        self._update_draft_status(token, status)

        record = ApprovedDraftRecord(
            token=token,
            mode=edited.mode,
            text=edited.final_text,
            tweets=edited.final_tweets,
            policy_report=report,
        )

        _, log = self.notifier.execute(record)
        logs.append(log)
        self._save_logs(run_state.run_id, logs)

    def _save_run(self, state: RunState) -> None:
        conn = get_connection()
        conn.execute(
            "INSERT INTO runs (run_id, created_at, status, agent_logs_json) VALUES (?, ?, ?, ?)",
            (state.run_id, state.created_at, state.status, "[]"),
        )
        conn.commit()
        conn.close()

    def _update_run_status(self, run_id: str, status: str, started_at: datetime, error: Optional[str]) -> None:
        finished = datetime.now(timezone.utc)
        duration_ms = int((finished - started_at).total_seconds() * 1000)
        conn = get_connection()
        if error:
            conn.execute(
                "UPDATE runs SET status=?, last_error=?, finished_at=?, duration_ms=? WHERE run_id=?",
                (status, error[:500], finished, duration_ms, run_id),
            )
        else:
            conn.execute(
                "UPDATE runs SET status=?, finished_at=?, duration_ms=? WHERE run_id=?",
                (status, finished, duration_ms, run_id),
            )
        conn.commit()
        conn.close()

    def _save_logs(self, run_id: str, logs: list[AgentLog]) -> None:
        conn = get_connection()
        logs_json = json.dumps([l.model_dump(mode="json") for l in logs])
        conn.execute("UPDATE runs SET agent_logs_json=? WHERE run_id=?", (logs_json, run_id))
        conn.commit()
        conn.close()

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
    ) -> str:
        token = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=int(getattr(settings, "TOKEN_TTL_HOURS", 36) or 36))
        status = "pending" if report.action == "PASS" else "needs_human_attention"
        tweets_json = json.dumps(edited.final_tweets) if edited.mode == "thread" and edited.final_tweets else None
        thread_plan_json = thread_plan.model_dump_json() if thread_plan else None

        conn = get_connection()
        conn.execute(
            """
            INSERT INTO drafts (
                token, run_id, created_at, expires_at, status,
                token_consumed, thread_enabled, thread_plan_json, tweets_json,
                materials_json, topic_plan_json, style_profile_json,
                candidates_json, edited_draft_json, policy_report_json,
                final_text
            ) VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                token,
                run_id,
                now,
                expires,
                status,
                1 if edited.mode == "thread" else 0,
                thread_plan_json,
                tweets_json,
                materials.model_dump_json(),
                plan.model_dump_json(),
                style.model_dump_json(),
                candidates.model_dump_json(),
                edited.model_dump_json(),
                report.model_dump_json(),
                edited.final_text or (edited.final_tweets[0] if edited.final_tweets else ""),
            ),
        )
        conn.commit()
        conn.close()
        return token

    def _update_draft_status(self, token: str, status: str) -> None:
        conn = get_connection()
        conn.execute("UPDATE drafts SET status=? WHERE token=?", (status, token))
        conn.commit()
        conn.close()

    def _update_policy_report(self, token: str, report: PolicyReport) -> None:
        conn = get_connection()
        conn.execute(
            "UPDATE drafts SET policy_report_json=?, status=? WHERE token=?",
            (report.model_dump_json(), "pending" if report.action == "PASS" else "needs_human_attention", token),
        )
        conn.commit()
        conn.close()

    def _update_draft_generation(
        self,
        token: str,
        candidates: DraftCandidates,
        edited: EditedDraft,
        report: PolicyReport,
        style: StyleProfile,
        thread_plan: ThreadPlan,
    ) -> None:
        tweets_json = json.dumps(edited.final_tweets) if edited.mode == "thread" and edited.final_tweets else None
        conn = get_connection()
        conn.execute(
            """
            UPDATE drafts
            SET candidates_json=?, edited_draft_json=?, policy_report_json=?, final_text=?, tweets_json=?,
                style_profile_json=?, thread_plan_json=?, status=?
            WHERE token=?
            """,
            (
                candidates.model_dump_json(),
                edited.model_dump_json(),
                report.model_dump_json(),
                edited.final_text or (edited.final_tweets[0] if edited.final_tweets else ""),
                tweets_json,
                style.model_dump_json(),
                thread_plan.model_dump_json(),
                "pending" if report.action == "PASS" else "needs_human_attention",
                token,
            ),
        )
        conn.commit()
        conn.close()

    def _get_recent_posts(self, days: int = 14, limit: int = 200) -> list[str]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        conn = get_connection()
        rows = conn.execute(
            "SELECT content FROM posts WHERE posted_at > ? ORDER BY posted_at DESC LIMIT ?",
            (cutoff, limit),
        ).fetchall()
        conn.close()
        return [r[0] for r in rows if r[0]]

    def _get_posts_in_window(self, start: datetime, end: datetime) -> list[str]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT content FROM posts WHERE posted_at >= ? AND posted_at < ? ORDER BY posted_at DESC",
            (start, end),
        ).fetchall()
        conn.close()
        return [r[0] for r in rows if r[0]]

    def _save_style_profile(self, profile: StyleProfile) -> None:
        conn = get_connection()
        conn.execute(
            "INSERT INTO style_profiles (created_at, profile_json) VALUES (datetime('now'), ?)",
            (profile.model_dump_json(),),
        )
        conn.commit()
        conn.close()

    def _write_style_cache(self, profile: StyleProfile) -> None:
        try:
            with open("style_profile.json", "w", encoding="utf-8") as f:
                f.write(profile.model_dump_json())
        except Exception:
            return

    def _get_style_profile(self) -> StyleProfile:
        conn = get_connection()
        row = conn.execute(
            "SELECT profile_json FROM style_profiles ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if row and row[0]:
            try:
                return StyleProfile(**json.loads(row[0]))
            except Exception:
                pass
        try:
            if os.path.exists("style_profile.json"):
                with open("style_profile.json", "r", encoding="utf-8") as f:
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

    def _get_style_profile_from_row(self, row) -> StyleProfile:
        try:
            if "style_profile_json" in row.keys() and row["style_profile_json"]:
                return StyleProfile(**json.loads(row["style_profile_json"]))
        except Exception:
            pass
        return self._get_style_profile()

    def _save_weekly_report(self, report: WeeklyReport) -> None:
        conn = get_connection()
        conn.execute(
            """
            INSERT INTO weekly_reports (week_start, week_end, report_json, created_at)
            VALUES (?, ?, ?, datetime('now'))
            """,
            (report.week_start, report.week_end, report.model_dump_json()),
        )
        conn.commit()
        conn.close()


def _is_expired(expires_at_value) -> bool:
    try:
        if isinstance(expires_at_value, str):
            expires_at = datetime.fromisoformat(expires_at_value)
        else:
            expires_at = expires_at_value
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) > expires_at
    except Exception:
        return False


orchestrator = Orchestrator()
