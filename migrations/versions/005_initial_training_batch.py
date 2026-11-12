"""Initial training batch sizing (100 jobs, 60-day corpus).

Revision ID: 005
Revises: 004
Create Date: 2026-08-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    scoring_config = sa.table(
        "scoring_config",
        sa.column("key", sa.String),
        sa.column("value", postgresql.JSONB),
        sa.column("description", sa.Text),
    )
    op.bulk_insert(
        scoring_config,
        [
            {
                "key": "backfill_deck_cap",
                "value": {"count": 100},
                "description": "Initial signup training deck size",
            },
            {
                "key": "backfill_max_jobs_per_employer",
                "value": {"count": 10},
                "description": "Max jobs per employer in the initial training deck",
            },
        ],
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM scoring_config WHERE key IN "
            "('backfill_deck_cap', 'backfill_max_jobs_per_employer')"
        )
    )
