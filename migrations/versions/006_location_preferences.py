"""Location preferences and geo cache tables.

Revision ID: 006
Revises: 005
Create Date: 2026-08-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: str | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "hard_constraints",
        sa.Column("max_commute_minutes", sa.Integer(), nullable=True),
    )
    op.add_column(
        "hard_constraints",
        sa.Column(
            "remote_openness",
            sa.String(length=32),
            nullable=False,
            server_default="open_to_remote",
        ),
    )
    op.add_column(
        "jobs",
        sa.Column("geocoded_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "location_geocode_cache",
        sa.Column("normalized_key", sa.String(length=512), primary_key=True),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("formatted_name", sa.String(length=512), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=True),
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
    )

    op.create_table(
        "route_cache",
        sa.Column("origin_geohash", sa.String(length=16), primary_key=True),
        sa.Column("dest_geohash", sa.String(length=16), primary_key=True),
        sa.Column("drive_minutes", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=True),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "geo_api_usage",
        sa.Column("month", sa.String(length=7), primary_key=True),
        sa.Column("geocode_calls", sa.Integer(), server_default="0", nullable=False),
        sa.Column("geocode_calls_today", sa.Integer(), server_default="0", nullable=False),
        sa.Column("geocode_day", sa.String(length=10), nullable=True),
        sa.Column("matrix_elements", sa.Integer(), server_default="0", nullable=False),
    )

    op.execute(
        """
        UPDATE hard_constraints
        SET max_commute_minutes = COALESCE(location_radius_miles, 45)
        WHERE remote_openness = 'open_to_remote'
        """
    )


def downgrade() -> None:
    op.drop_table("geo_api_usage")
    op.drop_table("route_cache")
    op.drop_table("location_geocode_cache")
    op.drop_column("jobs", "geocoded_at")
    op.drop_column("hard_constraints", "remote_openness")
    op.drop_column("hard_constraints", "max_commute_minutes")
