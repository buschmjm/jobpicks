"""Add user-facing label to application packets."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "026"
down_revision: str | None = "025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "application_packets",
        sa.Column("label", sa.String(length=256), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("application_packets", "label")
