"""Revenue prerequisites: referrals, email unsubscribe tokens (Workstream C)."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "021"
down_revision: str | None = "020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("referral_code", sa.String(length=16), nullable=True))
    op.add_column("users", sa.Column("referred_by_user_id", sa.Uuid(), nullable=True))
    op.add_column("users", sa.Column("email_unsubscribe_token", sa.String(length=64), nullable=True))
    op.create_foreign_key(
        "fk_users_referred_by_user_id",
        "users",
        "users",
        ["referred_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_users_referral_code", "users", ["referral_code"], unique=True)
    op.create_index(
        "ix_users_email_unsubscribe_token",
        "users",
        ["email_unsubscribe_token"],
        unique=True,
    )

    op.create_table(
        "referral_redemptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("referrer_user_id", sa.Uuid(), nullable=False),
        sa.Column("referee_user_id", sa.Uuid(), nullable=False),
        sa.Column("reward_days", sa.Integer(), nullable=False, server_default="90"),
        sa.Column(
            "redeemed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["referrer_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["referee_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("referee_user_id", name="uq_referral_redemptions_referee"),
    )
    op.create_index(
        "ix_referral_redemptions_referrer",
        "referral_redemptions",
        ["referrer_user_id", "redeemed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_referral_redemptions_referrer", table_name="referral_redemptions")
    op.drop_table("referral_redemptions")
    op.drop_index("ix_users_email_unsubscribe_token", table_name="users")
    op.drop_index("ix_users_referral_code", table_name="users")
    op.drop_constraint("fk_users_referred_by_user_id", "users", type_="foreignkey")
    op.drop_column("users", "email_unsubscribe_token")
    op.drop_column("users", "referred_by_user_id")
    op.drop_column("users", "referral_code")
