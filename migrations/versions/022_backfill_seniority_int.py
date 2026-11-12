"""Backfill seniority_int on jobs and profiles (Workstream F follow-up)."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "022"
down_revision: str | None = "021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _backfill_jobs(bind: sa.Connection) -> None:
    from core.seniority import derive_seniority_from_title, seniority_to_int

    rows = bind.execute(
        sa.text(
            "SELECT id, seniority_level, title, seniority_int "
            "FROM jobs WHERE seniority_int IS NULL"
        )
    ).mappings()
    for row in rows:
        if row["seniority_level"]:
            level = seniority_to_int(row["seniority_level"])
        else:
            level = derive_seniority_from_title(row["title"] or "")
        bind.execute(
            sa.text("UPDATE jobs SET seniority_int = :level WHERE id = :id"),
            {"level": level, "id": row["id"]},
        )


def _backfill_profiles(bind: sa.Connection) -> None:
    from core.seniority import seniority_to_int

    rows = bind.execute(
        sa.text(
            "SELECT id, seniority_level, seniority_int "
            "FROM profiles WHERE seniority_int IS NULL"
        )
    ).mappings()
    for row in rows:
        level = seniority_to_int(row["seniority_level"]) if row["seniority_level"] else 2
        bind.execute(
            sa.text("UPDATE profiles SET seniority_int = :level WHERE id = :id"),
            {"level": level, "id": row["id"]},
        )


def upgrade() -> None:
    bind = op.get_bind()
    _backfill_jobs(bind)
    _backfill_profiles(bind)


def downgrade() -> None:
    op.execute(sa.text("UPDATE jobs SET seniority_int = NULL"))
    op.execute(sa.text("UPDATE profiles SET seniority_int = NULL"))
