"""Add apply_url, ats_type, ats_metadata to jobs."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "012"
down_revision: str | None = "011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("apply_url", sa.String(length=2048), nullable=True))
    op.add_column("jobs", sa.Column("ats_type", sa.String(length=32), nullable=True))
    op.add_column(
        "jobs",
        sa.Column(
            "ats_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.execute("UPDATE jobs SET apply_url = source_url WHERE apply_url IS NULL AND source_url IS NOT NULL")
    op.create_index("ix_jobs_ats_type", "jobs", ["ats_type"])


def downgrade() -> None:
    op.drop_index("ix_jobs_ats_type", table_name="jobs")
    op.drop_column("jobs", "ats_metadata")
    op.drop_column("jobs", "ats_type")
    op.drop_column("jobs", "apply_url")
