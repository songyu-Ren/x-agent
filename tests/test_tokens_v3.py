from __future__ import annotations

from datetime import UTC, datetime, timedelta

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
from infrastructure.db import repositories as db
from infrastructure.db.session import get_sessionmaker


def test_action_token_hash_and_ttl_and_consumption(clean_db):
    now = datetime.now(UTC)
    with get_sessionmaker()() as session:
        db.create_run(session, run_id="run1", source="test", created_at=now)
        draft = db.create_draft(
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
        raw = db.issue_action_token(
            session, draft=draft, action="approve", ttl_seconds=60, one_time=True
        )
        session.commit()

    with get_sessionmaker()() as session:
        d, token_row, status = db.resolve_action_token(
            session, action="approve", raw_token=raw, now=now
        )
        assert status == "ok"
        assert d is not None
        assert token_row is not None
        assert token_row.token_hash == db.hash_action_token(raw)

        d2, token_row2, status2 = db.resolve_action_token(
            session, action="approve", raw_token=raw, now=now + timedelta(seconds=61)
        )
        assert status2 == "expired"
        assert d2 is None
        assert token_row2 is not None

    with get_sessionmaker()() as session:
        d3, token_row3, status3 = db.resolve_action_token(
            session, action="approve", raw_token=raw, now=now
        )
        assert status3 == "ok"
        assert token_row3 is not None
        db.consume_action_token(session, token_row3, consumed_at=now)
        session.commit()

    with get_sessionmaker()() as session:
        d4, _, status4 = db.resolve_action_token(session, action="approve", raw_token=raw, now=now)
        assert status4 == "consumed"
        assert d4 is None
