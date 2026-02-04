from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


def _json_type():
    return JSONB().with_variant(JSON(), "sqlite")


class Base(DeclarativeBase):
    pass


class Run(Base):
    __tablename__ = "runs"

    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="scheduler")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="running")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)

    drafts: Mapped[list[Draft]] = relationship(back_populates="run", cascade="all, delete-orphan")
    agent_logs: Mapped[list[AgentLog]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class Draft(Base):
    __tablename__ = "drafts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.run_id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending", index=True)

    token_consumed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    thread_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    thread_plan_json: Mapped[dict | None] = mapped_column(_json_type(), nullable=True)
    tweets_json: Mapped[list[str] | None] = mapped_column(_json_type(), nullable=True)

    materials_json: Mapped[dict] = mapped_column(_json_type(), nullable=False)
    topic_plan_json: Mapped[dict] = mapped_column(_json_type(), nullable=False)
    style_profile_json: Mapped[dict] = mapped_column(_json_type(), nullable=False)
    candidates_json: Mapped[dict] = mapped_column(_json_type(), nullable=False)
    edited_draft_json: Mapped[dict] = mapped_column(_json_type(), nullable=False)
    policy_report_json: Mapped[dict] = mapped_column(_json_type(), nullable=False)

    final_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    published_tweet_ids_json: Mapped[list[str] | None] = mapped_column(_json_type(), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)

    approval_idempotency_key: Mapped[str | None] = mapped_column(
        String(80), nullable=True, unique=True
    )

    run: Mapped[Run] = relationship(back_populates="drafts")
    posts: Mapped[list[Post]] = relationship(back_populates="draft", cascade="all, delete-orphan")
    action_tokens: Mapped[list[ActionToken]] = relationship(
        back_populates="draft", cascade="all, delete-orphan"
    )
    publish_attempts: Mapped[list[PublishAttempt]] = relationship(
        back_populates="draft", cascade="all, delete-orphan"
    )
    policy_reports: Mapped[list[PolicyReport]] = relationship(
        back_populates="draft", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list[AuditLog]] = relationship(
        back_populates="draft", cascade="all, delete-orphan"
    )


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    draft_id: Mapped[str] = mapped_column(ForeignKey("drafts.id"), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    tweet_id: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    publish_idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)

    draft: Mapped[Draft] = relationship(back_populates="posts")

    __table_args__ = (Index("ix_posts_draft_position", "draft_id", "position", unique=True),)


class PublishAttempt(Base):
    __tablename__ = "publish_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    draft_id: Mapped[str] = mapped_column(ForeignKey("drafts.id"), nullable=False, index=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    owner: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="started", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)

    draft: Mapped[Draft] = relationship(back_populates="publish_attempts")

    __table_args__ = (
        Index("ix_publish_attempts_draft_attempt", "draft_id", "attempt", unique=True),
    )


class ActionToken(Base):
    __tablename__ = "action_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    draft_id: Mapped[str] = mapped_column(ForeignKey("drafts.id"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    one_time: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    draft: Mapped[Draft] = relationship(back_populates="action_tokens")

    __table_args__ = (Index("ix_action_tokens_action_draft", "action", "draft_id"),)


class AgentLog(Base):
    __tablename__ = "agent_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.run_id"), nullable=False, index=True)

    agent_name: Mapped[str] = mapped_column(String(80), nullable=False)
    start_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    input_summary: Mapped[str] = mapped_column(String(200), nullable=False)
    output_summary: Mapped[str] = mapped_column(String(200), nullable=False)
    model_used: Mapped[str | None] = mapped_column(String(120), nullable=True)
    errors: Mapped[str | None] = mapped_column(String(500), nullable=True)
    warnings_json: Mapped[list[str]] = mapped_column(_json_type(), nullable=False, default=list)

    run: Mapped[Run] = relationship(back_populates="agent_logs")


class PolicyReport(Base):
    __tablename__ = "policy_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    draft_id: Mapped[str] = mapped_column(ForeignKey("drafts.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    report_json: Mapped[dict] = mapped_column(_json_type(), nullable=False)

    draft: Mapped[Draft] = relationship(back_populates="policy_reports")


class StyleProfile(Base):
    __tablename__ = "style_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    profile_json: Mapped[dict] = mapped_column(_json_type(), nullable=False)


class WeeklyReport(Base):
    __tablename__ = "weekly_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    week_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    week_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    report_json: Mapped[dict] = mapped_column(_json_type(), nullable=False)

    __table_args__ = (Index("ix_weekly_reports_window", "week_start", "week_end", unique=True),)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False, default="admin", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    sessions: Mapped[list[UserSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list[AuditLog]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    csrf_token: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(50), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(200), nullable=True)

    user: Mapped[User] = relationship(back_populates="sessions")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    draft_id: Mapped[str | None] = mapped_column(ForeignKey("drafts.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    ip_address: Mapped[str | None] = mapped_column(String(50), nullable=True)
    details_json: Mapped[dict] = mapped_column(_json_type(), nullable=False)

    user: Mapped[User] = relationship(back_populates="audit_logs")
    draft: Mapped[Draft | None] = relationship(back_populates="audit_logs")


Index("ix_drafts_created_at", Draft.created_at)
