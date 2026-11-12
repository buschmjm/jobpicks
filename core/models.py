"""SQLAlchemy 2.0 ORM models for the v1 schema (plan §13)."""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base


class FactStatus(str, enum.Enum):
    CONFIRMED = "confirmed"
    INFERRED = "inferred"
    NEEDS_CONFIRMATION = "needs_confirmation"


class RemoteMode(str, enum.Enum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNKNOWN = "unknown"


class JobStatus(str, enum.Enum):
    OPEN = "open"
    CLOSED = "closed"


class QueueSlotType(str, enum.Enum):
    CORE = "core"
    EXPLORE = "explore"


class QueueState(str, enum.Enum):
    QUEUED = "queued"
    SWIPED_RIGHT = "swiped_right"
    SWIPED_LEFT = "swiped_left"
    SKIPPED = "skipped"
    EXPIRED = "expired"


class TodoStatus(str, enum.Enum):
    TO_APPLY = "to_apply"
    APPLIED = "applied"
    ARCHIVED = "archived"


class ApplicationPacketStatus(str, enum.Enum):
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"
    OPENED = "opened"
    APPLIED = "applied"


class SwipeReason(str, enum.Enum):
    NOT_QUALIFIED = "not_qualified"
    OVERQUALIFIED = "overqualified"
    COMP_TOO_LOW = "comp_too_low"
    LOCATION_REMOTE = "location_remote"
    DONT_WANT_WORK = "dont_want_work"
    COMPANY = "company"


class FeedbackAction(str, enum.Enum):
    SWIPE_RIGHT = "swipe_right"
    SWIPE_LEFT = "swipe_left"
    SKIP = "skip"
    EXPIRED_UNSWIPED = "expired_unswiped"
    TODO_APPLIED = "todo_applied"
    TODO_ARCHIVED = "todo_archived"


class EventType(str, enum.Enum):
    QUEUE_BACKFILLED = "queue_backfilled"
    QUEUE_TOPPED_UP = "queue_topped_up"
    CARD_VIEWED = "card_viewed"
    SWIPE_RIGHT = "swipe_right"
    SWIPE_LEFT = "swipe_left"
    SKIP = "skip"
    EXPIRED_UNSWIPED = "expired_unswiped"
    TODO_ADDED = "todo_added"
    APPLIED_CLICKED = "applied_clicked"
    APPLIED_SELFREPORT = "applied_selfreport"
    TODO_ARCHIVED = "todo_archived"
    DIGEST_SENT = "digest_sent"
    DIGEST_OPENED = "digest_opened"
    DIGEST_SUBSCRIBED = "digest_subscribed"
    INTRADAY_ALERT_SENT = "intraday_alert_sent"
    REFERRAL_REDEEMED = "referral_redeemed"
    SUBSCRIPTION_CANCELED = "subscription_canceled"
    PAGE_VIEW = "page_view"
    DECK_OPENED = "deck_opened"
    SETTINGS_OPENED = "settings_opened"
    PROFILE_UPDATED = "profile_updated"
    LOGIN = "login"
    UNSUBSCRIBED = "unsubscribed"


class QueueJobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    plan_tier: Mapped[str] = mapped_column(String(16), nullable=False, server_default="free")
    stripe_customer_id: Mapped[str | None] = mapped_column(String(128))
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(128))
    subscription_status: Mapped[str | None] = mapped_column(String(32))
    price_variant_cents: Mapped[int | None] = mapped_column(Integer)
    subscription_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    referral_code: Mapped[str | None] = mapped_column(String(16))
    referred_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    email_unsubscribe_token: Mapped[str | None] = mapped_column(String(64))
    timezone: Mapped[str | None] = mapped_column(String(64))
    unsubscribed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    profile: Mapped[Profile | None] = relationship(back_populates="user", uselist=False)
    hard_constraints: Mapped[HardConstraints | None] = relationship(
        back_populates="user", uselist=False
    )
    preference_weights: Mapped[list[PreferenceWeights]] = relationship(
        back_populates="user"
    )
    queue_items: Mapped[list[UserJobQueue]] = relationship(back_populates="user")
    todo_items: Mapped[list[TodoItem]] = relationship(back_populates="user")
    feedback_events: Mapped[list[FeedbackEvent]] = relationship(back_populates="user")
    events: Mapped[list[Event]] = relationship(back_populates="user")
    digests: Mapped[list[Digest]] = relationship(back_populates="user")
    engagement: Mapped[UserEngagement | None] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    contributed_search_terms: Mapped[list[SearchTerm]] = relationship(
        back_populates="contributed_by_user"
    )
    career_messages: Mapped[list[CareerMessage]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    resume_drafts: Mapped[list[ResumeDraft]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    resume_variants: Mapped[list[ResumeVariant]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    resume_builder_messages: Mapped[list[ResumeBuilderMessage]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    resume_proposals: Mapped[list[ResumeProposal]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    application_packets: Mapped[list[ApplicationPacket]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    saved_application_answers: Mapped[list[SavedApplicationAnswer]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    created_skills: Mapped[list[Skill]] = relationship(back_populates="created_by_user")
    referred_by: Mapped[User | None] = relationship(
        remote_side="User.id",
        foreign_keys="User.referred_by_user_id",
    )
    referral_redemptions_made: Mapped[list[ReferralRedemption]] = relationship(
        back_populates="referrer",
        foreign_keys="ReferralRedemption.referrer_user_id",
    )

    __table_args__ = (
        Index("ix_users_email", "email"),
        Index("ix_users_stripe_customer_id", "stripe_customer_id", unique=True),
        Index("ix_users_stripe_subscription_id", "stripe_subscription_id", unique=True),
        Index("ix_users_referral_code", "referral_code", unique=True),
        Index("ix_users_email_unsubscribe_token", "email_unsubscribe_token", unique=True),
    )


class Profile(Base):
    """Parsed resume JSONB plus structured columns; facts carry FactStatus in JSON."""

    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    parsed_resume: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    headline: Mapped[str | None] = mapped_column(String(512))
    summary: Mapped[str | None] = mapped_column(Text)
    target_titles: Mapped[list[str] | None] = mapped_column(JSONB)
    skills: Mapped[list[str] | None] = mapped_column(JSONB)
    seniority_level: Mapped[str | None] = mapped_column(String(64))
    seniority_int: Mapped[int | None] = mapped_column(Integer)
    years_experience: Mapped[float | None] = mapped_column(Float)
    industries: Mapped[list[str] | None] = mapped_column(JSONB)
    locations: Mapped[list[Any] | None] = mapped_column(JSONB)
    remote_preference: Mapped[str | None] = mapped_column(String(32))
    salary_target_min: Mapped[int | None] = mapped_column(Integer)
    free_text_wants: Mapped[str | None] = mapped_column(Text)
    taste_embedding: Mapped[list[float] | None] = mapped_column(Vector(768))
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    default_application_steps: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    awaiting_deck_backfill: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    last_backfill_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="profile")
    skill_links: Mapped[list[ProfileSkill]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    experiences: Mapped[list[ProfileExperience]] = relationship(
        back_populates="profile", cascade="all, delete-orphan", order_by="ProfileExperience.sort_order"
    )
    education_rows: Mapped[list[ProfileEducation]] = relationship(
        back_populates="profile", cascade="all, delete-orphan", order_by="ProfileEducation.sort_order"
    )

    __table_args__ = (Index("ix_profiles_user_id", "user_id"),)


class Skill(Base):
    """Shared skill directory — users pick existing names or create new ones."""

    __tablename__ = "skills"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(80), nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    use_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    created_by_user: Mapped[User | None] = relationship(back_populates="created_skills")
    aliases: Mapped[list[SkillAlias]] = relationship(
        back_populates="skill", cascade="all, delete-orphan"
    )
    profile_links: Mapped[list[ProfileSkill]] = relationship(back_populates="skill")
    job_links: Mapped[list[JobSkill]] = relationship(back_populates="skill")

    __table_args__ = (
        UniqueConstraint("normalized_name", name="uq_skills_normalized_name"),
        Index("ix_skills_normalized_name", "normalized_name"),
        Index("ix_skills_use_count", "use_count"),
    )


class SkillAlias(Base):
    __tablename__ = "skill_aliases"

    id: Mapped[uuid.UUID] = _uuid_pk()
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False
    )
    normalized_name: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    skill: Mapped[Skill] = relationship(back_populates="aliases")

    __table_args__ = (
        UniqueConstraint("normalized_name", name="uq_skill_aliases_normalized_name"),
        Index("ix_skill_aliases_skill_id", "skill_id"),
    )


class ProfileSkill(Base):
    __tablename__ = "profile_skills"

    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    profile: Mapped[Profile] = relationship(back_populates="skill_links")
    skill: Mapped[Skill] = relationship(back_populates="profile_links")

    __table_args__ = (Index("ix_profile_skills_skill_id", "skill_id"),)


class ProfileExperience(Base):
    __tablename__ = "profile_experiences"

    id: Mapped[uuid.UUID] = _uuid_pk()
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL")
    )
    company_name: Mapped[str] = mapped_column(String(512), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    location: Mapped[str | None] = mapped_column(String(512))
    start_date: Mapped[str | None] = mapped_column(String(32))
    end_date: Mapped[str | None] = mapped_column(String(32))
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    highlights: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default="[]")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    profile: Mapped[Profile] = relationship(back_populates="experiences")
    company: Mapped[Company | None] = relationship()

    __table_args__ = (Index("ix_profile_experiences_profile_id", "profile_id"),)


class ProfileEducation(Base):
    __tablename__ = "profile_education"

    id: Mapped[uuid.UUID] = _uuid_pk()
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    institution: Mapped[str] = mapped_column(String(512), nullable=False)
    degree: Mapped[str | None] = mapped_column(String(128))
    field: Mapped[str | None] = mapped_column(String(256))
    end_date: Mapped[str | None] = mapped_column(String(32))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    profile: Mapped[Profile] = relationship(back_populates="education_rows")

    __table_args__ = (Index("ix_profile_education_profile_id", "profile_id"),)


class HardConstraints(Base):
    __tablename__ = "hard_constraints"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    min_salary: Mapped[int | None] = mapped_column(Integer)
    locations: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    location_radius_miles: Mapped[int | None] = mapped_column(Integer)
    max_commute_minutes: Mapped[int | None] = mapped_column(Integer)
    remote_openness: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="open_to_remote"
    )
    remote_acceptability: Mapped[dict[str, bool] | None] = mapped_column(JSONB)
    never_industries: Mapped[list[str] | None] = mapped_column(JSONB)
    blocked_companies: Mapped[list[str] | None] = mapped_column(JSONB)
    work_authorization: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="hard_constraints")

    __table_args__ = (Index("ix_hard_constraints_user_id", "user_id"),)


class LocationGeocodeCache(Base):
    __tablename__ = "location_geocode_cache"

    normalized_key: Mapped[str] = mapped_column(String(512), primary_key=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    formatted_name: Mapped[str | None] = mapped_column(String(512))
    source: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class RouteCache(Base):
    __tablename__ = "route_cache"

    origin_geohash: Mapped[str] = mapped_column(String(16), primary_key=True)
    dest_geohash: Mapped[str] = mapped_column(String(16), primary_key=True)
    drive_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str | None] = mapped_column(String(32))
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class GeoApiUsage(Base):
    __tablename__ = "geo_api_usage"

    month: Mapped[str] = mapped_column(String(7), primary_key=True)
    geocode_calls: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    geocode_calls_today: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    geocode_day: Mapped[str | None] = mapped_column(String(10))
    matrix_elements: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class PreferenceWeights(Base):
    """Versioned per-user facet weights and taste vector snapshots."""

    __tablename__ = "preference_weights"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    weights: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    facet_boosts: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    taste_embedding: Mapped[list[float] | None] = mapped_column(Vector(768))
    right_swipe_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="preference_weights")

    __table_args__ = (
        UniqueConstraint("user_id", "version", name="uq_preference_weights_user_version"),
        Index("ix_preference_weights_user_id_is_current", "user_id", "is_current"),
    )


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(512), nullable=False)
    slug: Mapped[str | None] = mapped_column(String(256))
    website: Mapped[str | None] = mapped_column(String(2048))
    industry: Mapped[str | None] = mapped_column(String(256))
    size_band: Mapped[str | None] = mapped_column(String(64))
    greenhouse_board_token: Mapped[str | None] = mapped_column(String(256))
    lever_site_name: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    jobs: Mapped[list[Job]] = relationship(back_populates="company")

    __table_args__ = (
        Index("ix_companies_normalized_name", "normalized_name"),
        Index("ix_companies_name", "name"),
    )


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL")
    )
    company_name: Mapped[str] = mapped_column(String(512), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_title: Mapped[str] = mapped_column(String(512), nullable=False)
    location_text: Mapped[str | None] = mapped_column(String(512))
    city: Mapped[str | None] = mapped_column(String(128))
    state: Mapped[str | None] = mapped_column(String(64))
    country: Mapped[str | None] = mapped_column(String(64))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    geocoded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    remote_mode: Mapped[RemoteMode] = mapped_column(
        String(16), nullable=False, server_default=RemoteMode.UNKNOWN.value
    )
    employment_type: Mapped[str | None] = mapped_column(String(64))
    salary_min: Mapped[int | None] = mapped_column(Integer)
    salary_max: Mapped[int | None] = mapped_column(Integer)
    salary_currency: Mapped[str | None] = mapped_column(String(8))
    salary_period: Mapped[str | None] = mapped_column(String(16))
    date_posted: Mapped[date | None] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(Text)
    requirements: Mapped[str | None] = mapped_column(Text)
    skills: Mapped[list[str] | None] = mapped_column(JSONB)
    seniority_level: Mapped[str | None] = mapped_column(String(64))
    seniority_int: Mapped[int | None] = mapped_column(Integer)
    primary_source: Mapped[str | None] = mapped_column(String(64))
    source_url: Mapped[str | None] = mapped_column(String(2048))
    apply_url: Mapped[str | None] = mapped_column(String(2048))
    ats_type: Mapped[str | None] = mapped_column(String(32))
    ats_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    canonical_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    embedding: Mapped[list[float] | None] = mapped_column(Vector(768))
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    status: Mapped[JobStatus] = mapped_column(
        String(16), nullable=False, server_default=JobStatus.OPEN.value
    )
    is_direct: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    company: Mapped[Company | None] = relationship(back_populates="jobs")
    sources: Mapped[list[JobSource]] = relationship(back_populates="job")
    queue_items: Mapped[list[UserJobQueue]] = relationship(back_populates="job")
    todo_items: Mapped[list[TodoItem]] = relationship(back_populates="job")
    feedback_events: Mapped[list[FeedbackEvent]] = relationship(back_populates="job")
    skill_links: Mapped[list[JobSkill]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_jobs_canonical_hash", "canonical_hash"),
        Index("ix_jobs_status_first_seen", "status", "first_seen"),
        Index("ix_jobs_company_name", "company_name"),
        Index("ix_jobs_date_posted", "date_posted"),
        Index("ix_jobs_ats_type", "ats_type"),
        Index(
            "ix_jobs_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


class JobSkill(Base):
    __tablename__ = "job_skills"

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    job: Mapped[Job] = relationship(back_populates="skill_links")
    skill: Mapped[Skill] = relationship(back_populates="job_links")

    __table_args__ = (Index("ix_job_skills_skill_id", "skill_id"),)


class JobSource(Base):
    """Provenance record linking a job to an upstream source."""

    __tablename__ = "job_sources"

    id: Mapped[uuid.UUID] = _uuid_pk()
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    source_name: Mapped[str] = mapped_column(String(64), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(512))
    source_url: Mapped[str | None] = mapped_column(String(2048))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    job: Mapped[Job] = relationship(back_populates="sources")

    __table_args__ = (
        UniqueConstraint(
            "source_name", "external_id", name="uq_job_sources_source_external_id"
        ),
        Index("ix_job_sources_job_id", "job_id"),
        Index("ix_job_sources_source_name", "source_name"),
    )


class UserJobQueue(Base):
    __tablename__ = "user_job_queue"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    score: Mapped[float | None] = mapped_column(Numeric(8, 4))
    explain: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    score_components: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    is_stretch: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    slot_type: Mapped[QueueSlotType] = mapped_column(
        String(16), nullable=False, server_default=QueueSlotType.CORE.value
    )
    state: Mapped[QueueState] = mapped_column(
        String(32), nullable=False, server_default=QueueState.QUEUED.value
    )
    reason: Mapped[SwipeReason | None] = mapped_column(String(32))
    enqueued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    swiped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="queue_items")
    job: Mapped[Job] = relationship(back_populates="queue_items")

    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_user_job_queue_user_job"),
        Index("ix_user_job_queue_user_state_enqueued", "user_id", "state", "enqueued_at"),
        Index("ix_user_job_queue_user_score", "user_id", "score"),
    )


class TodoItem(Base):
    __tablename__ = "todo_items"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[TodoStatus] = mapped_column(
        String(16), nullable=False, server_default=TodoStatus.TO_APPLY.value
    )
    application_steps: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="todo_items")
    job: Mapped[Job] = relationship(back_populates="todo_items")
    application_packet: Mapped[ApplicationPacket | None] = relationship(
        back_populates="todo_item", uselist=False
    )

    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_todo_items_user_job"),
        Index("ix_todo_items_user_status", "user_id", "status"),
    )


class UserEngagement(Base):
    __tablename__ = "user_engagement"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    streak_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    longest_streak: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_active_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    milestones: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="engagement")


class SearchTerm(Base):
    """Global search term set with optional contributor attribution."""

    __tablename__ = "search_terms"

    id: Mapped[uuid.UUID] = _uuid_pk()
    term: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    normalized_term: Mapped[str] = mapped_column(String(512), nullable=False)
    contributed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    contributed_by_user: Mapped[User | None] = relationship(
        back_populates="contributed_search_terms"
    )

    __table_args__ = (
        Index("ix_search_terms_normalized_term", "normalized_term"),
        Index("ix_search_terms_is_active", "is_active"),
        Index("ix_search_terms_last_fetched_at", "last_fetched_at"),
    )


class CareerMessage(Base):
    """Career advisor chat messages (single thread per user in v1)."""

    __tablename__ = "career_messages"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(String(16))
    status: Mapped[str | None] = mapped_column(String(16))
    sources: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="career_messages")

    __table_args__ = (Index("ix_career_messages_user_created", "user_id", "created_at"),)


class ResumeVariant(Base):
    """Named resume tailoring context (slug + label) for conversational builder."""

    __tablename__ = "resume_variants"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    headline: Mapped[str | None] = mapped_column(Text)
    summary_override: Mapped[str | None] = mapped_column(Text)
    target_titles: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    emphasis_notes: Mapped[str | None] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="resume_variants")
    messages: Mapped[list[ResumeBuilderMessage]] = relationship(back_populates="variant")
    proposals: Mapped[list[ResumeProposal]] = relationship(back_populates="variant")

    __table_args__ = (
        UniqueConstraint("user_id", "slug", name="uq_resume_variants_user_slug"),
        Index("ix_resume_variants_user_id", "user_id"),
    )


class ResumeBuilderMessage(Base):
    """Conversational resume builder chat messages (per user + optional variant)."""

    __tablename__ = "resume_builder_messages"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("resume_variants.id", ondelete="SET NULL")
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    proposal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resume_proposals.id", ondelete="SET NULL", use_alter=True),
    )
    source: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="resume_builder_messages")
    variant: Mapped[ResumeVariant | None] = relationship(back_populates="messages")

    __table_args__ = (
        Index(
            "ix_resume_builder_messages_user_variant_created",
            "user_id",
            "variant_id",
            "created_at",
        ),
    )


class ResumeProposal(Base):
    """Pending or applied profile edits proposed by the resume builder."""

    __tablename__ = "resume_proposals"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("resume_variants.id", ondelete="SET NULL")
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resume_builder_messages.id", ondelete="SET NULL", use_alter=True),
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    proposal_type: Mapped[str] = mapped_column(Text, nullable=False)
    operations: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    preview_summary: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="resume_proposals")
    variant: Mapped[ResumeVariant | None] = relationship(back_populates="proposals")

    __table_args__ = (Index("ix_resume_proposals_user_status", "user_id", "status"),)


class ResumeDraft(Base):
    """Structured resume document (master or job-tailored) for HTML export."""

    __tablename__ = "resume_drafts"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="draft")
    layout: Mapped[str] = mapped_column(String(32), nullable=False, server_default="ats")
    # Full jobdeck.resume.v1 document (header, roles, skills, selection flags).
    document: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="resume_drafts")

    __table_args__ = (
        Index("ix_resume_drafts_user_updated", "user_id", "updated_at"),
        Index("ix_resume_drafts_user_job", "user_id", "job_id"),
    )


class ApplicationPacket(Base):
    """Prepared application content for review before opening Apply Browser."""

    __tablename__ = "application_packets"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    todo_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("todo_items.id", ondelete="CASCADE")
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=ApplicationPacketStatus.GENERATING.value
    )
    apply_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    ats_type: Mapped[str | None] = mapped_column(String(32))
    label: Mapped[str | None] = mapped_column(String(256))
    fit_verdict: Mapped[str | None] = mapped_column(String(32))
    fit_rationale: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default="[]")
    identity: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    resume_draft_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("resume_drafts.id", ondelete="SET NULL")
    )
    resume_pdf_path: Mapped[str | None] = mapped_column(String(512))
    cover_letter: Mapped[str | None] = mapped_column(Text)
    answers: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default="[]")
    generation_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="application_packets")
    job: Mapped[Job] = relationship()
    todo_item: Mapped[TodoItem | None] = relationship(back_populates="application_packet")
    resume_draft: Mapped[ResumeDraft | None] = relationship()

    __table_args__ = (
        Index(
            "ix_application_packets_user_todo",
            "user_id",
            "todo_item_id",
            unique=True,
            postgresql_where="todo_item_id IS NOT NULL",
        ),
        Index("ix_application_packets_user_updated", "user_id", "updated_at"),
    )


class SavedApplicationAnswer(Base):
    """Reusable screening answers saved from application packets."""

    __tablename__ = "saved_application_answers"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    question_key: Mapped[str] = mapped_column(String(128), nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="saved_application_answers")

    __table_args__ = (
        UniqueConstraint("user_id", "question_key", name="uq_saved_application_answers_user_key"),
        Index("ix_saved_application_answers_user_last_used", "user_id", "last_used_at"),
    )


class FeedbackEvent(Base):
    """Append-only behavioral feedback for preference learning."""

    __tablename__ = "feedback_events"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[FeedbackAction] = mapped_column(String(32), nullable=False)
    reason: Mapped[SwipeReason | None] = mapped_column(String(32))
    dwell_seconds: Mapped[float | None] = mapped_column(Float)
    session_id: Mapped[str | None] = mapped_column(String(64))
    signal_weight: Mapped[float | None] = mapped_column(Float)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="feedback_events")
    job: Mapped[Job] = relationship(back_populates="feedback_events")

    __table_args__ = (
        Index("ix_feedback_events_user_created_at", "user_id", "created_at"),
        Index("ix_feedback_events_job_id", "job_id"),
        Index("ix_feedback_events_action", "action"),
    )


class Event(Base):
    """Append-only product analytics events (plan §11)."""

    __tablename__ = "events"

    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    type: Mapped[EventType] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped[User | None] = relationship(back_populates="events")

    __table_args__ = (
        Index("ix_events_user_created_at", "user_id", "created_at"),
        Index("ix_events_type_created_at", "type", "created_at"),
        Index("ix_events_created_at", "created_at"),
    )


class ScoringConfig(Base):
    """Tunable scoring weights and half-lives (plan §10)."""

    __tablename__ = "scoring_config"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Digest(Base):
    __tablename__ = "digests"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    new_jobs_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    top_job_ids: Mapped[list[str] | None] = mapped_column(JSONB)
    email_subject: Mapped[str | None] = mapped_column(String(512))
    tracking_token: Mapped[str | None] = mapped_column(String(128), unique=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="digests")

    __table_args__ = (
        Index("ix_digests_user_sent_at", "user_id", "sent_at"),
        Index("ix_digests_tracking_token", "tracking_token"),
    )


class ReferralRedemption(Base):
    __tablename__ = "referral_redemptions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    referrer_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    referee_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    reward_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="90")
    redeemed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    referrer: Mapped[User] = relationship(
        back_populates="referral_redemptions_made",
        foreign_keys=[referrer_user_id],
    )
    referee: Mapped[User] = relationship(foreign_keys=[referee_user_id])

    __table_args__ = (
        Index("ix_referral_redemptions_referrer", "referrer_user_id", "redeemed_at"),
    )


class LlmCallLog(Base):
    __tablename__ = "llm_call_logs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    feature: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    time_to_first_token_ms: Mapped[int | None] = mapped_column(Integer)
    total_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_llm_call_logs_feature_created", "feature", "created_at"),
        Index("ix_llm_call_logs_user_created", "user_id", "created_at"),
    )


class TitleEmbeddingCache(Base):
    __tablename__ = "title_embedding_cache"

    title_key: Mapped[str] = mapped_column(Text, primary_key=True)
    title_display: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class QueueJob(Base):
    """Postgres-backed worker queue (SELECT ... FOR UPDATE SKIP LOCKED)."""

    __tablename__ = "queue_jobs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    job_type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    status: Mapped[QueueJobStatus] = mapped_column(
        String(16), nullable=False, server_default=QueueJobStatus.PENDING.value
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="3")
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index("ix_queue_jobs_status_scheduled_at", "status", "scheduled_at"),
        Index("ix_queue_jobs_job_type_status", "job_type", "status"),
    )


class DailyUsageCounter(Base):
    __tablename__ = "daily_usage_counters"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    feature: Mapped[str] = mapped_column(String(64), nullable=False)
    usage_date: Mapped[date] = mapped_column(Date, nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    user: Mapped[User] = relationship()

    __table_args__ = (
        UniqueConstraint("user_id", "feature", "usage_date", name="uq_daily_usage_user_feature_date"),
        Index("ix_daily_usage_user_feature_date", "user_id", "feature", "usage_date"),
    )


class MonthlyUsageCounter(Base):
    __tablename__ = "monthly_usage_counters"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    feature: Mapped[str] = mapped_column(String(64), nullable=False)
    usage_month: Mapped[date] = mapped_column(Date, nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    user: Mapped[User] = relationship()

    __table_args__ = (
        UniqueConstraint("user_id", "feature", "usage_month", name="uq_monthly_usage_user_feature_month"),
        Index("ix_monthly_usage_user_feature_month", "user_id", "feature", "usage_month"),
    )
