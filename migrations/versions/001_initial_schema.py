"""Initial v1 schema with pgvector extension and HNSW index.

Revision ID: 001
Revises:
Create Date: 2026-08-27

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("timezone", sa.String(length=64), nullable=True),
        sa.Column("unsubscribed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "companies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("normalized_name", sa.String(length=512), nullable=False),
        sa.Column("slug", sa.String(length=256), nullable=True),
        sa.Column("website", sa.String(length=2048), nullable=True),
        sa.Column("industry", sa.String(length=256), nullable=True),
        sa.Column("size_band", sa.String(length=64), nullable=True),
        sa.Column("greenhouse_board_token", sa.String(length=256), nullable=True),
        sa.Column("lever_site_name", sa.String(length=256), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_companies_normalized_name", "companies", ["normalized_name"])
    op.create_index("ix_companies_name", "companies", ["name"])

    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("company_name", sa.String(length=512), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("normalized_title", sa.String(length=512), nullable=False),
        sa.Column("location_text", sa.String(length=512), nullable=True),
        sa.Column("city", sa.String(length=128), nullable=True),
        sa.Column("state", sa.String(length=64), nullable=True),
        sa.Column("country", sa.String(length=64), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column(
            "remote_mode",
            sa.String(length=16),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("employment_type", sa.String(length=64), nullable=True),
        sa.Column("salary_min", sa.Integer(), nullable=True),
        sa.Column("salary_max", sa.Integer(), nullable=True),
        sa.Column("salary_currency", sa.String(length=8), nullable=True),
        sa.Column("salary_period", sa.String(length=16), nullable=True),
        sa.Column("date_posted", sa.Date(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("requirements", sa.Text(), nullable=True),
        sa.Column("skills", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("seniority_level", sa.String(length=64), nullable=True),
        sa.Column("primary_source", sa.String(length=64), nullable=True),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column("canonical_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "raw",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("embedding", Vector(768), nullable=True),
        sa.Column(
            "first_seen",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_seen",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column("is_direct", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_jobs_canonical_hash", "jobs", ["canonical_hash"])
    op.create_index("ix_jobs_status_first_seen", "jobs", ["status", "first_seen"])
    op.create_index("ix_jobs_company_name", "jobs", ["company_name"])
    op.create_index("ix_jobs_date_posted", "jobs", ["date_posted"])
    op.execute(
        """
        CREATE INDEX ix_jobs_embedding_hnsw ON jobs
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )

    op.create_table(
        "profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "parsed_resume",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("headline", sa.String(length=512), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("target_titles", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("skills", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("seniority_level", sa.String(length=64), nullable=True),
        sa.Column("years_experience", sa.Float(), nullable=True),
        sa.Column("industries", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("locations", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("remote_preference", sa.String(length=32), nullable=True),
        sa.Column("salary_target_min", sa.Integer(), nullable=True),
        sa.Column("free_text_wants", sa.Text(), nullable=True),
        sa.Column("taste_embedding", Vector(768), nullable=True),
        sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", name="uq_profiles_user_id"),
    )
    op.create_index("ix_profiles_user_id", "profiles", ["user_id"])

    op.create_table(
        "hard_constraints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("min_salary", sa.Integer(), nullable=True),
        sa.Column("locations", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("location_radius_miles", sa.Integer(), nullable=True),
        sa.Column("remote_acceptability", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("never_industries", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("blocked_companies", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("work_authorization", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", name="uq_hard_constraints_user_id"),
    )
    op.create_index("ix_hard_constraints_user_id", "hard_constraints", ["user_id"])

    op.create_table(
        "preference_weights",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "weights",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("facet_boosts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("taste_embedding", Vector(768), nullable=True),
        sa.Column("right_swipe_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "version", name="uq_preference_weights_user_version"),
    )
    op.create_index(
        "ix_preference_weights_user_id_is_current",
        "preference_weights",
        ["user_id", "is_current"],
    )

    op.create_table(
        "job_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_name", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=512), nullable=True),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "source_name", "external_id", name="uq_job_sources_source_external_id"
        ),
    )
    op.create_index("ix_job_sources_job_id", "job_sources", ["job_id"])
    op.create_index("ix_job_sources_source_name", "job_sources", ["source_name"])

    op.create_table(
        "user_job_queue",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("score", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("explain", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("slot_type", sa.String(length=16), nullable=False, server_default="core"),
        sa.Column("state", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("reason", sa.String(length=32), nullable=True),
        sa.Column(
            "enqueued_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("swiped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "job_id", name="uq_user_job_queue_user_job"),
    )
    op.create_index(
        "ix_user_job_queue_user_state_enqueued",
        "user_job_queue",
        ["user_id", "state", "enqueued_at"],
    )
    op.create_index("ix_user_job_queue_user_score", "user_job_queue", ["user_id", "score"])

    op.create_table(
        "todo_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="to_apply"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "job_id", name="uq_todo_items_user_job"),
    )
    op.create_index("ix_todo_items_user_status", "todo_items", ["user_id", "status"])

    op.create_table(
        "search_terms",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("term", sa.String(length=512), nullable=False),
        sa.Column("normalized_term", sa.String(length=512), nullable=False),
        sa.Column("contributed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["contributed_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint("term", name="uq_search_terms_term"),
    )
    op.create_index("ix_search_terms_normalized_term", "search_terms", ["normalized_term"])
    op.create_index("ix_search_terms_is_active", "search_terms", ["is_active"])

    op.create_table(
        "feedback_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=32), nullable=True),
        sa.Column("dwell_seconds", sa.Float(), nullable=True),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("signal_weight", sa.Float(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_feedback_events_user_created_at",
        "feedback_events",
        ["user_id", "created_at"],
    )
    op.create_index("ix_feedback_events_job_id", "feedback_events", ["job_id"])
    op.create_index("ix_feedback_events_action", "feedback_events", ["action"])

    op.create_table(
        "events",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_events_user_created_at", "events", ["user_id", "created_at"])
    op.create_index("ix_events_type_created_at", "events", ["type", "created_at"])
    op.create_index("ix_events_created_at", "events", ["created_at"])

    op.create_table(
        "scoring_config",
        sa.Column("key", sa.String(length=128), primary_key=True),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "digests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("new_jobs_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("top_job_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("email_subject", sa.String(length=512), nullable=True),
        sa.Column("tracking_token", sa.String(length=128), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tracking_token", name="uq_digests_tracking_token"),
    )
    op.create_index("ix_digests_user_sent_at", "digests", ["user_id", "sent_at"])
    op.create_index("ix_digests_tracking_token", "digests", ["tracking_token"])

    op.create_table(
        "queue_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_type", sa.String(length=128), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column(
            "scheduled_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_queue_jobs_status_scheduled_at",
        "queue_jobs",
        ["status", "scheduled_at"],
    )
    op.create_index(
        "ix_queue_jobs_job_type_status",
        "queue_jobs",
        ["job_type", "status"],
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
                "key": "score_weights",
                "value": {
                    "w_sem": 0.35,
                    "w_skill": 0.25,
                    "w_comp": 0.15,
                    "w_level": 0.15,
                    "w_geo": 0.10,
                },
                "description": "Initial hybrid scoring weights (plan §10).",
            },
            {
                "key": "feedback_half_life_days",
                "value": {"days": 30},
                "description": "Exponential decay half-life for behavioral signals.",
            },
            {
                "key": "cold_start_right_swipe_threshold",
                "value": {"count": 20},
                "description": "Right-swipes before taste vector dominates scoring.",
            },
            {
                "key": "daily_queue_topup_cap",
                "value": {"count": 30},
                "description": "Max new queue cards appended per user per day.",
            },
            {
                "key": "explore_slot_ratio",
                "value": {"ratio": 0.1},
                "description": "Fraction of deck cards reserved for explore picks.",
            },
            {
                "key": "mindless_swipe_guard",
                "value": {"streak_threshold": 15, "min_dwell_seconds": 1.5},
                "description": "Session streak decay and low-dwell weight halving.",
            },
            {
                "key": "embedding_dimensions",
                "value": {"dimensions": 768, "model": "nomic-embed-text"},
                "description": "Embedding model dimensionality (plan §9).",
            },
        ],
    )


def downgrade() -> None:
    op.drop_table("queue_jobs")
    op.drop_table("digests")
    op.drop_table("scoring_config")
    op.drop_table("events")
    op.drop_table("feedback_events")
    op.drop_table("search_terms")
    op.drop_table("todo_items")
    op.drop_table("user_job_queue")
    op.drop_table("job_sources")
    op.drop_table("preference_weights")
    op.drop_table("hard_constraints")
    op.drop_table("profiles")
    op.execute("DROP INDEX IF EXISTS ix_jobs_embedding_hnsw")
    op.drop_table("jobs")
    op.drop_table("companies")
    op.drop_table("users")
    op.execute("DROP EXTENSION IF EXISTS vector")
