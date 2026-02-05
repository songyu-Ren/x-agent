from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0005_app_config"
down_revision = "0004_auth_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    json_type = JSONB().with_variant(sa.JSON(), "sqlite")

    op.create_table(
        "app_config",
        sa.Column("key", sa.String(length=80), primary_key=True),
        sa.Column("value_json", json_type, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_app_config_updated_at", "app_config", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_app_config_updated_at", table_name="app_config")
    op.drop_table("app_config")
