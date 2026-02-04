from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from sqlalchemy import select

from app.models import (
    AgentLog,
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
from infrastructure.db import models
from infrastructure.db import repositories as db
from infrastructure.db.session import get_sessionmaker


def _log(name: str) -> AgentLog:
    now = datetime.now(UTC)
    return AgentLog(
        agent_name=name,
        start_ts=now,
        end_ts=now,
        duration_ms=0,
        input_summary="",
        output_summary="",
    )


def test_orchestrator_creates_draft(clean_db, monkeypatch):
    monkeypatch.setattr(
        orchestrator.collector, "execute", lambda rs: (Materials(), _log("Collector"))
    )
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
    monkeypatch.setattr(
        orchestrator.notifier, "execute", lambda rec: (MagicMock(), _log("Notifier"))
    )

    run_id = orchestrator.start_run(source="manual")

    with get_sessionmaker()() as session:
        run = db.get_run(session, run_id)
        draft = session.execute(
            select(models.Draft).where(models.Draft.run_id == run_id)
        ).scalar_one_or_none()

    assert run is not None
    assert run.status == "completed"
    assert draft is not None
    assert draft.status == "pending"
    assert draft.final_text == "hello"


def test_orchestrator_approve_expired(clean_db):
    now = datetime.now(UTC)
    with get_sessionmaker()() as session:
        db.create_run(session, run_id="run1", source="test", created_at=now)
        draft = db.create_draft(
            session=session,
            run_id="run1",
            draft_id="draft_expired",
            token_hash="1" * 64,
            created_at=now,
            expires_at=now - timedelta(hours=1),
            status="pending",
            materials=Materials(),
            topic_plan=TopicPlan(topic_bucket=1, angles=["a"], key_points=["k"], evidence_map={}),
            style_profile=StyleProfile(),
            thread_plan=ThreadPlan(enabled=False, tweets_count=1),
            candidates=DraftCandidates(candidates=[DraftCandidate(mode="single", text="t")]),
            edited_draft=EditedDraft(
                mode="single",
                selected_candidate_index=0,
                original=DraftCandidate(mode="single", text="t"),
                final_text="t",
            ),
            policy_report=PolicyReport(checks=[], risk_level="LOW", action="PASS"),
        )
        approve_token = db.issue_action_token(
            session=session, draft=draft, action="approve", ttl_seconds=0, one_time=True
        )
        session.commit()

    code, msg = orchestrator.approve_draft(approve_token)
    assert code == 410
