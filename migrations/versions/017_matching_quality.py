"""Raise match floors and add title-fit / skill-coverage scoring keys."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "017"
down_revision: str | None = "016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE scoring_config
            SET value = to_jsonb(0.42::numeric)
            WHERE key = 'min_match_score'
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE scoring_config
            SET value = to_jsonb(0.30::numeric)
            WHERE key = 'min_explore_score'
            """
        )
    )
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
                "key": "min_title_fit_for_core",
                "value": 0.12,
                "description": "Minimum title overlap for core deck slots",
            },
        ],
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE scoring_config
            SET value = to_jsonb(0.35::numeric)
            WHERE key = 'min_match_score'
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE scoring_config
            SET value = to_jsonb(0.25::numeric)
            WHERE key = 'min_explore_score'
            """
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM scoring_config
            WHERE key = 'min_title_fit_for_core'
            """
        )
    )
