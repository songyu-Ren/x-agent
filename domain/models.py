from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class RunAction(str, Enum):
    PASS = "PASS"
    REWRITE = "REWRITE"
    HOLD = "HOLD"
    ERROR = "ERROR"
    WAIT_HUMAN = "WAIT_HUMAN"


class AgentLog(BaseModel):
    agent_name: str
    start_ts: datetime
    end_ts: datetime
    duration_ms: int
    input_summary: str
    output_summary: str
    model_used: str | None = None
    errors: str | None = None
    warnings: list[str] = []


class EvidenceItem(BaseModel):
    source_name: str
    source_id: str
    timestamp: datetime
    raw_snippet: str
    title: str | None = None
    url: str | None = None


class Materials(BaseModel):
    git_commits: list[EvidenceItem] = []
    devlog: EvidenceItem | None = None
    notes: list[EvidenceItem] = []
    links: list[EvidenceItem] = []
    errors: list[str] = []


class EvidenceRef(BaseModel):
    source_name: str
    source_id: str
    quote: str


class TopicPlan(BaseModel):
    topic_bucket: int
    angles: list[str]
    key_points: list[str]
    evidence_map: dict[str, list[EvidenceRef]] = {}


class StyleProfile(BaseModel):
    preferred_openers: list[str] = []
    forbidden_phrases: list[str] = []
    sentence_length_preference: str = "short"
    tone_rules: list[str] = []
    formatting_rules: list[str] = []


class ThreadPlan(BaseModel):
    enabled: bool
    tweets_count: int
    numbering_enabled: bool = True
    reason: str = ""
    tweet_key_points: list[list[str]] = []
    evidence_map: dict[str, list[EvidenceRef]] = {}


class DraftCandidate(BaseModel):
    mode: str
    text: str | None = None
    tweets: list[str] | None = None


class DraftCandidates(BaseModel):
    candidates: list[DraftCandidate]


class EditedDraft(BaseModel):
    mode: str
    selected_candidate_index: int
    original: DraftCandidate
    final_text: str | None = None
    final_tweets: list[str] | None = None
    numbering_added: bool = False
    edit_notes: str = ""


class PolicyCheckResult(BaseModel):
    check_name: str
    passed: bool
    details: str


class PolicyReport(BaseModel):
    checks: list[PolicyCheckResult]
    risk_level: str
    action: str
    claims: list[str] = []
    evidence_map: dict[str, list[EvidenceRef]] = {}
    unsupported_claims: list[str] = []
    offending_spans: list[str] = []


class ApprovedDraftRecord(BaseModel):
    draft_id: str
    approve_token: str
    edit_token: str
    skip_token: str
    view_token: str
    mode: str
    text: str | None = None
    tweets: list[str] | None = None
    policy_report: PolicyReport


class NotificationResult(BaseModel):
    email_sent: bool
    whatsapp_sent: bool
    errors: list[str] = []


class PublishRequest(BaseModel):
    draft_id: str
    tweets: list[str]
    dry_run: bool
    reply_chain: bool = True


class PublishResult(BaseModel):
    tweet_ids: list[str] = []
    errors: list[str] = []


class WeeklyReport(BaseModel):
    week_start: datetime
    week_end: datetime
    top_topic_buckets: list[str] = []
    recommendations: list[str] = []
    next_week_topics: list[str] = []


class RunState(BaseModel):
    run_id: str
    created_at: datetime
    status: str = "running"
    source: str = "scheduler"

    action: RunAction = RunAction.PASS
    rewrite_count: int = 0
    max_rewrites: int = 1
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
