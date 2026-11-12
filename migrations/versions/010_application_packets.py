"""Add application_packets for prepare-confirm-apply flow."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "010"
down_revision: str | None = "009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "application_packets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("todo_item_id", sa.Uuid(), nullable=True),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="generating", nullable=False),
        sa.Column("apply_url", sa.String(length=2048), nullable=False),
        sa.Column("ats_type", sa.String(length=32), nullable=True),
        sa.Column("fit_verdict", sa.String(length=32), nullable=True),
        sa.Column(
            "fit_rationale",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "identity",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("resume_draft_id", sa.Uuid(), nullable=True),
        sa.Column("resume_pdf_path", sa.String(length=512), nullable=True),
        sa.Column("cover_letter", sa.Text(), nullable=True),
        sa.Column(
            "answers",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("generation_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resume_draft_id"], ["resume_drafts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["todo_item_id"], ["todo_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_application_packets_user_todo",
        "application_packets",
        ["user_id", "todo_item_id"],
        unique=True,
        postgresql_where=sa.text("todo_item_id IS NOT NULL"),
    )
    op.create_index(
        "ix_application_packets_user_updated",
        "application_packets",
        ["user_id", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_application_packets_user_updated", table_name="application_packets")
    op.drop_index("ix_application_packets_user_todo", table_name="application_packets")
    op.drop_table("application_packets")
