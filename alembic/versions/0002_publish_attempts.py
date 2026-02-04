from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0002_publish_attempts"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "publish_attempts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("draft_id", sa.String(length=36), sa.ForeignKey("drafts.id"), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("owner", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="started"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
    )
    op.create_index("ix_publish_attempts_draft_id", "publish_attempts", ["draft_id"])
    op.create_index("ix_publish_attempts_status", "publish_attempts", ["status"])
    op.create_index(
        "ix_publish_attempts_draft_attempt",
        "publish_attempts",
        ["draft_id", "attempt"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_publish_attempts_draft_attempt", table_name="publish_attempts")
    op.drop_index("ix_publish_attempts_status", table_name="publish_attempts")
    op.drop_index("ix_publish_attempts_draft_id", table_name="publish_attempts")
    op.drop_table("publish_attempts")
