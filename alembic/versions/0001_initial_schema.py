from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    json_type = JSONB().with_variant(sa.JSON(), "sqlite")

    op.create_table(
        "runs",
        sa.Column("run_id", sa.String(length=36), primary_key=True),
        sa.Column("source", sa.String(length=50), nullable=False, server_default="scheduler"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="running"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
    )

    op.create_table(
        "drafts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("token", sa.String(length=64), nullable=False, unique=True),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("runs.run_id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="pending"),
        sa.Column("token_consumed", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("thread_enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("thread_plan_json", json_type, nullable=True),
        sa.Column("tweets_json", json_type, nullable=True),
        sa.Column("materials_json", json_type, nullable=False),
        sa.Column("topic_plan_json", json_type, nullable=False),
        sa.Column("style_profile_json", json_type, nullable=False),
        sa.Column("candidates_json", json_type, nullable=False),
        sa.Column("edited_draft_json", json_type, nullable=False),
        sa.Column("policy_report_json", json_type, nullable=False),
        sa.Column("final_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("published_tweet_ids_json", json_type, nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("approval_idempotency_key", sa.String(length=80), nullable=True, unique=True),
    )
    op.create_index("ix_drafts_run_id", "drafts", ["run_id"])
    op.create_index("ix_drafts_status", "drafts", ["status"])
    op.create_index("ix_drafts_created_at", "drafts", ["created_at"])

    op.create_table(
        "posts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("draft_id", sa.String(length=36), sa.ForeignKey("drafts.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("tweet_id", sa.String(length=120), nullable=False, unique=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("publish_idempotency_key", sa.String(length=120), nullable=False, unique=True),
    )
    op.create_index("ix_posts_draft_id", "posts", ["draft_id"])
    op.create_index("ix_posts_draft_position", "posts", ["draft_id", "position"], unique=True)

    op.create_table(
        "agent_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("runs.run_id"), nullable=False),
        sa.Column("agent_name", sa.String(length=80), nullable=False),
        sa.Column("start_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("input_summary", sa.String(length=200), nullable=False),
        sa.Column("output_summary", sa.String(length=200), nullable=False),
        sa.Column("model_used", sa.String(length=120), nullable=True),
        sa.Column("errors", sa.String(length=500), nullable=True),
        sa.Column("warnings_json", json_type, nullable=False, server_default=sa.text("'[]'")),
    )
    op.create_index("ix_agent_logs_run_id", "agent_logs", ["run_id"])

    op.create_table(
        "policy_reports",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("draft_id", sa.String(length=36), sa.ForeignKey("drafts.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("risk_level", sa.String(length=20), nullable=False),
        sa.Column("report_json", json_type, nullable=False),
    )
    op.create_index("ix_policy_reports_draft_id", "policy_reports", ["draft_id"])

    op.create_table(
        "style_profiles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("profile_json", json_type, nullable=False),
    )

    op.create_table(
        "weekly_reports",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("week_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("week_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("report_json", json_type, nullable=False),
    )
    op.create_index(
        "ix_weekly_reports_window",
        "weekly_reports",
        ["week_start", "week_end"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_weekly_reports_window", table_name="weekly_reports")
    op.drop_table("weekly_reports")
    op.drop_table("style_profiles")
    op.drop_index("ix_policy_reports_draft_id", table_name="policy_reports")
    op.drop_table("policy_reports")
    op.drop_index("ix_agent_logs_run_id", table_name="agent_logs")
    op.drop_table("agent_logs")
    op.drop_index("ix_posts_draft_position", table_name="posts")
    op.drop_index("ix_posts_draft_id", table_name="posts")
    op.drop_table("posts")
    op.drop_index("ix_drafts_created_at", table_name="drafts")
    op.drop_index("ix_drafts_status", table_name="drafts")
    op.drop_index("ix_drafts_run_id", table_name="drafts")
    op.drop_table("drafts")
    op.drop_table("runs")
