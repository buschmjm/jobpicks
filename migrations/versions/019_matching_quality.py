"""Matching quality: seniority_int columns and stretch flag (Workstream F)."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "019"
down_revision: str | None = "018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("seniority_int", sa.Integer(), nullable=True))
    op.add_column("profiles", sa.Column("seniority_int", sa.Integer(), nullable=True))
    op.add_column(
        "user_job_queue",
        sa.Column("is_stretch", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_index("ix_jobs_seniority_int", "jobs", ["seniority_int"])


def downgrade() -> None:
    op.drop_index("ix_jobs_seniority_int", table_name="jobs")
    op.drop_column("user_job_queue", "is_stretch")
    op.drop_column("profiles", "seniority_int")
    op.drop_column("jobs", "seniority_int")
