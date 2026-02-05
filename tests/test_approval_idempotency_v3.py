from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models import (
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


def test_approve_is_idempotent_and_does_not_duplicate_posts(clean_db, monkeypatch):
    now = datetime.now(UTC)

    monkeypatch.setattr(
        orchestrator.policy,
        "execute",
        lambda inp: (PolicyReport(checks=[], risk_level="LOW", action="PASS"), None),
    )

    with get_sessionmaker()() as session:
        db.create_run(session, run_id="run1", source="test", created_at=now)
        db.create_draft(
            session=session,
            run_id="run1",
            draft_id="draft1",
            token_hash="1" * 64,
            created_at=now,
            expires_at=now + timedelta(hours=1),
            status="pending",
            materials=Materials(),
            topic_plan=TopicPlan(topic_bucket=1, angles=["a"], key_points=["k"], evidence_map={}),
            style_profile=StyleProfile(),
            thread_plan=ThreadPlan(enabled=True, tweets_count=2),
            candidates=DraftCandidates(candidates=[DraftCandidate(mode="thread", text="")]),
            edited_draft=EditedDraft(
                mode="thread",
                selected_candidate_index=0,
                original=DraftCandidate(mode="thread", text=""),
                final_text="tweet 1",
                final_tweets=["tweet 1", "tweet 2"],
            ),
            policy_report=PolicyReport(checks=[], risk_level="LOW", action="PASS"),
        )
        session.commit()

    code1, _ = orchestrator.approve_draft_by_id("draft1")
    code2, _ = orchestrator.approve_draft_by_id("draft1")
    assert code1 == 200
    assert code2 == 200

    with get_sessionmaker()() as session:
        draft = db.get_draft(session, "draft1")
        assert draft is not None
        assert draft.status in {"dry_run_posted", "posted"}
        posts = (
            session.execute(select(models.Post).where(models.Post.draft_id == "draft1"))
            .scalars()
            .all()
        )
        assert len(list(posts)) == 2
