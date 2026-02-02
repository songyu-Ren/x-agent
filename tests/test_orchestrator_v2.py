import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.database import get_connection
from app.models import (
    AgentLog,
    ApprovedDraftRecord,
    DraftCandidate,
    DraftCandidates,
    EditedDraft,
    Materials,
    PolicyReport,
    StyleProfile,
    ThreadPlan,
    TopicPlan,
)
from app.orchestrator import orchestrator


def _log(name: str) -> AgentLog:
    now = datetime.now(timezone.utc)
    return AgentLog(
        agent_name=name,
        start_ts=now,
        end_ts=now,
        duration_ms=0,
        input_summary="",
        output_summary="",
    )


def test_orchestrator_creates_draft(clean_db, monkeypatch):
    monkeypatch.setattr(orchestrator.collector, "execute", lambda rs: (Materials(), _log("Collector")))
    monkeypatch.setattr(
        orchestrator.curator,
        "execute",
        lambda inp: (
            TopicPlan(topic_bucket=1, angles=["a"], key_points=["k1", "k2"], evidence_map={}),
            _log("Curator"),
        ),
    )
    monkeypatch.setattr(
        orchestrator.thread_planner,
        "execute",
        lambda inp: (ThreadPlan(enabled=False, tweets_count=1), _log("ThreadPlanner")),
    )
    monkeypatch.setattr(
        orchestrator.writer,
        "execute",
        lambda inp: (
            DraftCandidates(candidates=[DraftCandidate(mode="single", text="hello")]),
            _log("Writer"),
        ),
    )
    monkeypatch.setattr(
        orchestrator.critic,
        "execute",
        lambda inp: (
            EditedDraft(
                mode="single",
                selected_candidate_index=0,
                original=DraftCandidate(mode="single", text="hello"),
                final_text="hello",
                edit_notes="",
            ),
            _log("Critic"),
        ),
    )
    monkeypatch.setattr(
        orchestrator.policy,
        "execute",
        lambda inp: (
            PolicyReport(checks=[], risk_level="LOW", action="PASS"),
            _log("Policy"),
        ),
    )
    monkeypatch.setattr(orchestrator.notifier, "execute", lambda rec: (MagicMock(), _log("Notifier")))

    run_id = orchestrator.start_run(source="manual")

    conn = get_connection()
    run = conn.execute("SELECT status FROM runs WHERE run_id=?", (run_id,)).fetchone()
    draft = conn.execute("SELECT token, status, final_text FROM drafts WHERE run_id=?", (run_id,)).fetchone()
    conn.close()

    assert run[0] == "completed"
    assert draft is not None
    assert draft[1] == "pending"
    assert draft[2] == "hello"


def test_orchestrator_approve_expired(clean_db):
    token = "tok_expired"
    now = datetime.now(timezone.utc)
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO drafts (
            token, run_id, created_at, expires_at, status,
            token_consumed, thread_enabled,
            materials_json, topic_plan_json, style_profile_json,
            candidates_json, edited_draft_json, policy_report_json,
            final_text
        ) VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            token,
            "run1",
            now,
            now - timedelta(hours=1),
            "pending",
            Materials().model_dump_json(),
            TopicPlan(topic_bucket=1, angles=["a"], key_points=["k"], evidence_map={}).model_dump_json(),
            StyleProfile().model_dump_json(),
            DraftCandidates(candidates=[DraftCandidate(mode="single", text="t")]).model_dump_json(),
            EditedDraft(
                mode="single",
                selected_candidate_index=0,
                original=DraftCandidate(mode="single", text="t"),
                final_text="t",
            ).model_dump_json(),
            PolicyReport(checks=[], risk_level="LOW", action="PASS").model_dump_json(),
            "t",
        ),
    )
    conn.commit()
    conn.close()

    code, msg = orchestrator.approve_draft(token)
    assert code == 410

