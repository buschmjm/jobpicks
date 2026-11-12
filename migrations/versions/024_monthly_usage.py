"""Monthly usage counters for Pro AI limits."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "024"
down_revision: str | None = "023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "monthly_usage_counters",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("feature", sa.String(length=64), nullable=False),
        sa.Column("usage_month", sa.Date(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "feature",
            "usage_month",
            name="uq_monthly_usage_user_feature_month",
        ),
    )
    op.create_index(
        "ix_monthly_usage_user_feature_month",
        "monthly_usage_counters",
        ["user_id", "feature", "usage_month"],
    )


def downgrade() -> None:
    op.drop_index("ix_monthly_usage_user_feature_month", table_name="monthly_usage_counters")
    op.drop_table("monthly_usage_counters")
