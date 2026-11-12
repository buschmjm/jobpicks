"""Add resume variants, builder messages, and profile change proposals."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "016"
down_revision: str | None = "015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "resume_variants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("headline", sa.Text(), nullable=True),
        sa.Column("summary_override", sa.Text(), nullable=True),
        sa.Column(
            "target_titles",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("emphasis_notes", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "slug", name="uq_resume_variants_user_slug"),
    )
    op.create_index("ix_resume_variants_user_id", "resume_variants", ["user_id"])

    op.create_table(
        "resume_proposals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("variant_id", sa.Uuid(), nullable=True),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("proposal_type", sa.Text(), nullable=False),
        sa.Column(
            "operations",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("preview_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["variant_id"], ["resume_variants.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_resume_proposals_user_status", "resume_proposals", ["user_id", "status"])

    op.create_table(
        "resume_builder_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("variant_id", sa.Uuid(), nullable=True),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("proposal_id", sa.Uuid(), nullable=True),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["variant_id"], ["resume_variants.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["proposal_id"], ["resume_proposals.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_resume_builder_messages_user_variant_created",
        "resume_builder_messages",
        ["user_id", "variant_id", "created_at"],
    )

    op.create_foreign_key(
        "fk_resume_proposals_message_id",
        "resume_proposals",
        "resume_builder_messages",
        ["message_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_resume_proposals_message_id", "resume_proposals", type_="foreignkey")
    op.drop_index(
        "ix_resume_builder_messages_user_variant_created",
        table_name="resume_builder_messages",
    )
    op.drop_table("resume_builder_messages")
    op.drop_index("ix_resume_proposals_user_status", table_name="resume_proposals")
    op.drop_table("resume_proposals")
    op.drop_index("ix_resume_variants_user_id", table_name="resume_variants")
    op.drop_table("resume_variants")
