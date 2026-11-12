"""AI performance telemetry, score components on queue cards, title embedding cache."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "018"
down_revision: str | None = "017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_call_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("feature", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("time_to_first_token_ms", sa.Integer(), nullable=True),
        sa.Column("total_ms", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_llm_call_logs_feature_created", "llm_call_logs", ["feature", "created_at"])
    op.create_index("ix_llm_call_logs_user_created", "llm_call_logs", ["user_id", "created_at"])

    op.add_column(
        "user_job_queue",
        sa.Column(
            "score_components",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )

    op.create_table(
        "title_embedding_cache",
        sa.Column("title_key", sa.Text(), nullable=False),
        sa.Column("title_display", sa.Text(), nullable=False),
        sa.Column("embedding", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("title_key"),
    )


def downgrade() -> None:
    op.drop_table("title_embedding_cache")
    op.drop_column("user_job_queue", "score_components")
    op.drop_index("ix_llm_call_logs_user_created", table_name="llm_call_logs")
    op.drop_index("ix_llm_call_logs_feature_created", table_name="llm_call_logs")
    op.drop_table("llm_call_logs")
