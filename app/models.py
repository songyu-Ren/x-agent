from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel


class RunState(BaseModel):
    run_id: str
    created_at: datetime
    status: str = "running"
    source: str = "scheduler"


class AgentLog(BaseModel):
    agent_name: str
    start_ts: datetime
    end_ts: datetime
    duration_ms: int
    input_summary: str
    output_summary: str
    model_used: Optional[str] = None
    errors: Optional[str] = None
    warnings: List[str] = []


class EvidenceItem(BaseModel):
    source_name: str
    source_id: str
    timestamp: datetime
    raw_snippet: str
    title: Optional[str] = None
    url: Optional[str] = None


class Materials(BaseModel):
    git_commits: List[EvidenceItem] = []
    devlog: Optional[EvidenceItem] = None
    notes: List[EvidenceItem] = []
    links: List[EvidenceItem] = []
    errors: List[str] = []


class EvidenceRef(BaseModel):
    source_name: str
    source_id: str
    quote: str


class TopicPlan(BaseModel):
    topic_bucket: int
    angles: List[str]
    key_points: List[str]
    evidence_map: Dict[str, List[EvidenceRef]] = {}


class StyleProfile(BaseModel):
    preferred_openers: List[str] = []
    forbidden_phrases: List[str] = []
    sentence_length_preference: str = "short"
    tone_rules: List[str] = []
    formatting_rules: List[str] = []


class ThreadPlan(BaseModel):
    enabled: bool
    tweets_count: int
    numbering_enabled: bool = True
    reason: str = ""
    tweet_key_points: List[List[str]] = []
    evidence_map: Dict[str, List[EvidenceRef]] = {}


class DraftCandidate(BaseModel):
    mode: str  # single|thread
    text: Optional[str] = None
    tweets: Optional[List[str]] = None


class DraftCandidates(BaseModel):
    candidates: List[DraftCandidate]


class EditedDraft(BaseModel):
    mode: str  # single|thread
    selected_candidate_index: int
    original: DraftCandidate
    final_text: Optional[str] = None
    final_tweets: Optional[List[str]] = None
    numbering_added: bool = False
    edit_notes: str = ""


class PolicyCheckResult(BaseModel):
    check_name: str
    passed: bool
    details: str


class PolicyReport(BaseModel):
    checks: List[PolicyCheckResult]
    risk_level: str  # LOW|MEDIUM|HIGH
    action: str  # PASS|REWRITE|HOLD
    claims: List[str] = []
    evidence_map: Dict[str, List[EvidenceRef]] = {}
    unsupported_claims: List[str] = []
    offending_spans: List[str] = []


class ApprovedDraftRecord(BaseModel):
    token: str
    mode: str
    text: Optional[str] = None
    tweets: Optional[List[str]] = None
    policy_report: PolicyReport


class NotificationResult(BaseModel):
    email_sent: bool
    whatsapp_sent: bool
    errors: List[str] = []


class PublishRequest(BaseModel):
    token: str
    tweets: List[str]
    dry_run: bool
    reply_chain: bool = True


class PublishResult(BaseModel):
    tweet_ids: List[str] = []
    errors: List[str] = []


class WeeklyReport(BaseModel):
    week_start: datetime
    week_end: datetime
    top_topic_buckets: List[str] = []
    recommendations: List[str] = []
    next_week_topics: List[str] = []

