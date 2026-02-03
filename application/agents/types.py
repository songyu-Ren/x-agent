from __future__ import annotations

from pydantic import BaseModel

from domain.models import (
    DraftCandidates,
    EditedDraft,
    Materials,
    PolicyReport,
    PublishResult,
    RunAction,
    StyleProfile,
    ThreadPlan,
    TopicPlan,
    WeeklyReport,
)


class RunStateDelta(BaseModel):
    action: RunAction | None = None
    last_error: str | None = None

    materials: Materials | None = None
    recent_posts: list[str] | None = None
    topic_plan: TopicPlan | None = None
    style_profile: StyleProfile | None = None
    thread_plan: ThreadPlan | None = None
    candidates: DraftCandidates | None = None
    edited_draft: EditedDraft | None = None
    policy_report: PolicyReport | None = None
    draft_token: str | None = None
    publish_result: PublishResult | None = None
    weekly_report: WeeklyReport | None = None
