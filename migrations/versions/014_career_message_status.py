"""Add status and sources to career_messages for async advisor replies."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "014"
down_revision: str | None = "013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "career_messages",
        sa.Column("status", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "career_messages",
        sa.Column("sources", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE career_messages
            SET status = 'complete'
            WHERE status IS NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_column("career_messages", "sources")
    op.drop_column("career_messages", "status")
