"""Stripe subscription columns on users (Workstream B)."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "020"
down_revision: str | None = "019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("plan_tier", sa.String(length=16), nullable=False, server_default="free"),
    )
    op.add_column("users", sa.Column("stripe_customer_id", sa.String(length=128), nullable=True))
    op.add_column("users", sa.Column("stripe_subscription_id", sa.String(length=128), nullable=True))
    op.add_column("users", sa.Column("subscription_status", sa.String(length=32), nullable=True))
    op.add_column("users", sa.Column("price_variant_cents", sa.Integer(), nullable=True))
    op.add_column(
        "users",
        sa.Column("subscription_period_end", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_stripe_customer_id", "users", ["stripe_customer_id"], unique=True)
    op.create_index(
        "ix_users_stripe_subscription_id",
        "users",
        ["stripe_subscription_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_users_stripe_subscription_id", table_name="users")
    op.drop_index("ix_users_stripe_customer_id", table_name="users")
    op.drop_column("users", "subscription_period_end")
    op.drop_column("users", "price_variant_cents")
    op.drop_column("users", "subscription_status")
    op.drop_column("users", "stripe_subscription_id")
    op.drop_column("users", "stripe_customer_id")
    op.drop_column("users", "plan_tier")
