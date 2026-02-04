from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.agents.publisher import PublisherAgent
from app.models import (
    DraftCandidate,
    DraftCandidates,
    EditedDraft,
    Materials,
    PolicyReport,
    PublishRequest,
    StyleProfile,
    ThreadPlan,
    TopicPlan,
)
from infrastructure.db import models
from infrastructure.db import repositories as db
from infrastructure.db.session import get_sessionmaker


def test_publisher_idempotent_thread_dry_run(clean_db):
    now = datetime.now(UTC)
    draft_id = "draft1"
    with get_sessionmaker()() as session:
        db.create_run(session, run_id="run1", source="test", created_at=now)
        db.create_draft(
            session=session,
            run_id="run1",
            draft_id=draft_id,
            token_hash="0" * 64,
            created_at=now,
            expires_at=now + timedelta(hours=1),
            status="pending",
            materials=Materials(),
            topic_plan=TopicPlan(topic_bucket=1, angles=["a"], key_points=["k"], evidence_map={}),
            style_profile=StyleProfile(),
            thread_plan=ThreadPlan(enabled=True, tweets_count=3),
            candidates=DraftCandidates(
                candidates=[DraftCandidate(mode="thread", text="t1\nt2\nt3")]
            ),
            edited_draft=EditedDraft(
                mode="thread",
                selected_candidate_index=0,
                original=DraftCandidate(mode="thread", text="t1\nt2\nt3"),
                final_text="t1",
                final_tweets=["t1", "t2", "t3"],
            ),
            policy_report=PolicyReport(checks=[], risk_level="LOW", action="PASS"),
        )
        session.commit()

    agent = PublisherAgent()
    req = PublishRequest(draft_id=draft_id, tweets=["t1", "t2", "t3"], dry_run=True)

    r1 = agent.run(req)
    r2 = agent.run(req)

    assert r1.tweet_ids == r2.tweet_ids

    with get_sessionmaker()() as session:
        draft = db.get_draft(session, draft_id)
        assert draft is not None
        rows = session.execute(
            select(models.Post.position, models.Post.tweet_id)
            .where(models.Post.draft_id == draft.id)
            .order_by(models.Post.position.asc())
        ).all()
        assert len(rows) == 3
