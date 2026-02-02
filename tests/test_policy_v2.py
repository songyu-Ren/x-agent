from datetime import datetime, timezone

from app.agents.policy import PolicyAgent
from app.models import (
    DraftCandidate,
    EditedDraft,
    EvidenceItem,
    Materials,
    StyleProfile,
)


def test_policy_fact_grounding_maps_evidence():
    agent = PolicyAgent()
    materials = Materials(
        git_commits=[
            EvidenceItem(
                source_name="git",
                source_id="abc",
                timestamp=datetime.now(timezone.utc),
                raw_snippet="Fix login redirect bug",
                title="Fix login redirect bug",
            )
        ],
        devlog=None,
        notes=[],
        links=[],
    )

    edited = EditedDraft(
        mode="single",
        selected_candidate_index=0,
        original=DraftCandidate(mode="single", text=""),
        final_text="Fixed login redirect bug and shipped it.",
        edit_notes="",
    )

    report = agent.run((edited, materials, [], StyleProfile()))
    assert any(c.check_name == "fact_grounded_ok" and c.passed for c in report.checks)
    assert report.action == "PASS"
    assert report.claims
    assert report.evidence_map


def test_policy_rejects_unsupported_claims():
    agent = PolicyAgent()
    materials = Materials(git_commits=[], devlog=None, notes=[], links=[])

    edited = EditedDraft(
        mode="single",
        selected_candidate_index=0,
        original=DraftCandidate(mode="single", text=""),
        final_text="Deployed a major refactor today.",
        edit_notes="",
    )

    report = agent.run((edited, materials, [], StyleProfile()))
    assert any(c.check_name == "fact_grounded_ok" and not c.passed for c in report.checks)
    assert report.action in ["REWRITE", "HOLD"]
    assert report.unsupported_claims

