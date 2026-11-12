"""Add last_fetched_at to search_terms for daily ingest rotation.

Revision ID: 007
Revises: 006
Create Date: 2026-08-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: str | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "search_terms",
        sa.Column("last_fetched_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_search_terms_last_fetched_at",
        "search_terms",
        ["last_fetched_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_search_terms_last_fetched_at", table_name="search_terms")
    op.drop_column("search_terms", "last_fetched_at")
