"""Profile-first scoring weights and match-score floors."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "013"
down_revision: str | None = "012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE scoring_config
            SET value = '{"w_sem": 0.38, "w_skill": 0.27, "w_comp": 0.10, "w_level": 0.15, "w_geo": 0.05, "w_title": 0.05}'::jsonb
            WHERE key = 'score_weights'
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
                "key": "min_match_score",
                "value": 0.35,
                "description": "Minimum hybrid score for core deck slots",
            },
            {
                "key": "min_explore_score",
                "value": 0.25,
                "description": "Minimum hybrid score for explore deck slots",
            },
            {
                "key": "cold_start_w_sem",
                "value": 0.25,
                "description": "Cold-start semantic weight before taste ramp",
            },
            {
                "key": "cold_start_w_skill",
                "value": 0.40,
                "description": "Cold-start skill weight before taste ramp",
            },
            {
                "key": "cold_start_w_title",
                "value": 0.10,
                "description": "Cold-start title hint weight before taste ramp",
            },
        ],
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE scoring_config
            SET value = '{"w_sem": 0.35, "w_skill": 0.25, "w_comp": 0.15, "w_level": 0.15, "w_geo": 0.10}'::jsonb
            WHERE key = 'score_weights'
            """
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM scoring_config
            WHERE key IN (
                'min_match_score',
                'min_explore_score',
                'cold_start_w_sem',
                'cold_start_w_skill',
                'cold_start_w_title'
            )
            """
        )
    )
