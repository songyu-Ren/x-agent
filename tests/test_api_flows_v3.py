from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
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


def test_api_login_list_drafts_and_edit_flow(clean_db, monkeypatch):
    now = datetime.now(UTC)
    with get_sessionmaker()() as session:
        _ = db.ensure_user(session, username="admin", raw_password="pw", role="admin")
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
        session.commit()

    import app.web as web

    monkeypatch.setattr(
        web.orchestrator,
        "policy_check_by_id",
        lambda draft_id, texts: (200, PolicyReport(checks=[], risk_level="LOW", action="PASS")),
    )
    monkeypatch.setattr(
        web.orchestrator,
        "save_edit_by_id",
        lambda draft_id, texts: (200, PolicyReport(checks=[], risk_level="LOW", action="PASS")),
    )
    monkeypatch.setattr(web.orchestrator, "approve_draft_by_id", lambda draft_id: (200, "ok"))

    client = TestClient(app)

    csrf = client.get("/api/auth/csrf")
    assert csrf.status_code == 200
    csrf_token = csrf.json()["csrf_token"]

    login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "pw", "csrf_token": csrf_token},
    )
    assert login.status_code == 200

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    api_csrf = me.json()["csrf_token"]

    drafts = client.get("/api/drafts")
    assert drafts.status_code == 200
    assert drafts.json()["items"]

    detail = client.get("/api/drafts/draft1")
    assert detail.status_code == 200

    policy_check = client.post(
        "/api/drafts/draft1/edit",
        headers={"x-csrf-token": api_csrf},
        json={"texts": ["updated"], "save": False},
    )
    assert policy_check.status_code == 200
    assert policy_check.json()["policy_report"]["action"] == "PASS"

    save = client.post(
        "/api/drafts/draft1/edit",
        headers={"x-csrf-token": api_csrf},
        json={"texts": ["updated"], "save": True},
    )
    assert save.status_code == 200

    approve = client.post("/api/drafts/draft1/approve", headers={"x-csrf-token": api_csrf})
    assert approve.status_code == 200
