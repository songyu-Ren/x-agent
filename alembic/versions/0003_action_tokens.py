from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0003_action_tokens"
down_revision = "0002_publish_attempts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "action_tokens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("draft_id", sa.String(length=36), sa.ForeignKey("drafts.id"), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("one_time", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("token_hash", name="uq_action_tokens_token_hash"),
    )
    op.create_index("ix_action_tokens_draft_id", "action_tokens", ["draft_id"])
    op.create_index("ix_action_tokens_action", "action_tokens", ["action"])
    op.create_index("ix_action_tokens_token_hash", "action_tokens", ["token_hash"])
    op.create_index("ix_action_tokens_action_draft", "action_tokens", ["action", "draft_id"])


def downgrade() -> None:
    op.drop_index("ix_action_tokens_action_draft", table_name="action_tokens")
    op.drop_index("ix_action_tokens_token_hash", table_name="action_tokens")
    op.drop_index("ix_action_tokens_action", table_name="action_tokens")
    op.drop_index("ix_action_tokens_draft_id", table_name="action_tokens")
    op.drop_table("action_tokens")
