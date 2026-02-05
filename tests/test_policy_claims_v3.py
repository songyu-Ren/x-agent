from __future__ import annotations

from app.agents.policy import PolicyAgent
from app.models import DraftCandidate, EditedDraft, Materials, StyleProfile


def test_policy_claim_extractor_skips_opinions(clean_db):
    agent = PolicyAgent()
    edited = EditedDraft(
        mode="single",
        selected_candidate_index=0,
        original=DraftCandidate(mode="single", text=""),
        final_text="I think this is great.",
        edit_notes="",
    )
    report = agent.run((edited, Materials(), [], StyleProfile()))
    assert report.action == "PASS"
    assert report.claims == []
