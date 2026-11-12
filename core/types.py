"""Shared dataclasses for scoring and preference learning."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum


class RemoteMode(StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNKNOWN = "unknown"


class RemoteOpenness(StrEnum):
    LOCAL_ONLY = "local_only"
    OPEN_TO_REMOTE = "open_to_remote"
    REMOTE_ONLY = "remote_only"


class FeedbackAction(StrEnum):
    SWIPE_RIGHT = "swipe_right"
    SWIPE_LEFT = "swipe_left"
    SKIP = "skip"
    EXPIRED_UNSWIPED = "expired_unswiped"
    TODO_APPLIED = "todo_applied"
    TODO_ARCHIVED = "todo_archived"


class RejectionReason(StrEnum):
    NOT_QUALIFIED = "not qualified"
    OVERQUALIFIED = "overqualified"
    COMP_TOO_LOW = "comp too low"
    LOCATION_REMOTE = "location/remote"
    DONT_WANT_THIS_WORK = "don't want this kind of work"
    COMPANY = "company"


@dataclass(frozen=True)
class ScoringConfig:
    """Mirrors scoring_config table intent — all tunables live here, not in code."""

    w_sem: float = 0.38
    w_skill: float = 0.27
    w_comp: float = 0.10
    w_level: float = 0.15
    w_geo: float = 0.05

    cold_start_right_swipe_threshold: int = 20
    cold_start_w_sem: float = 0.25
    cold_start_w_skill: float = 0.40

    signal_half_life_days: float = 30.0

    mindless_streak_threshold: int = 15
    mindless_streak_decay: float = 0.5
    min_dwell_seconds: float = 1.5
    low_dwell_weight_multiplier: float = 0.5

    max_weight_delta_per_event: float = 0.05
    max_weight_delta_per_day: float = 0.20

    explore_slot_ratio: float = 0.10
    max_jobs_per_employer_per_day: int = 3
    backfill_max_jobs_per_employer: int = 10

    max_job_age_days: int = 14
    daily_topup_cap: int = 30
    backfill_deck_cap: int = 100

    cold_start_w_title: float = 0.10
    w_title: float = 0.05

    min_match_score: float = 0.42
    min_explore_score: float = 0.30
    min_title_fit_for_core: float = 0.12
    skill_coverage_ratio: float = 1.0

    base_signal_strength: dict[str, float] = field(
        default_factory=lambda: {
            FeedbackAction.TODO_APPLIED.value: 1.0,
            FeedbackAction.SWIPE_RIGHT.value: 0.8,
            FeedbackAction.SKIP.value: -0.15,
            FeedbackAction.EXPIRED_UNSWIPED.value: -0.10,
            FeedbackAction.SWIPE_LEFT.value: -0.5,
            FeedbackAction.SWIPE_LEFT.value + "_with_reason": -0.7,
            FeedbackAction.TODO_ARCHIVED.value: -0.2,
        }
    )


@dataclass
class HardConstraints:
    min_salary: float | None = None
    allowed_remote_modes: frozenset[RemoteMode] = field(
        default_factory=lambda: frozenset(
            {RemoteMode.REMOTE, RemoteMode.HYBRID, RemoteMode.ONSITE, RemoteMode.UNKNOWN}
        )
    )
    home_lat: float | None = None
    home_lon: float | None = None
    max_commute_radius_miles: float | None = None
    max_commute_minutes: int | None = None
    remote_openness: RemoteOpenness = RemoteOpenness.OPEN_TO_REMOTE
    blocked_industries: frozenset[str] = field(default_factory=frozenset)
    requires_work_authorization: bool = False
    user_has_work_authorization: bool = True
    blocked_companies: frozenset[str] = field(default_factory=frozenset)


@dataclass
class UserProfile:
    user_id: str
    skills: frozenset[str] = field(default_factory=frozenset)
    seniority_level: int = 2
    target_salary: float = 100_000.0
    taste_embedding: tuple[float, ...] | None = None
    profile_prior_embedding: tuple[float, ...] | None = None
    target_titles: tuple[str, ...] = field(default_factory=tuple)
    stated_facet_weights: dict[str, float] = field(default_factory=dict)
    learned_facet_weights: dict[str, float] = field(default_factory=dict)
    home_lat: float | None = None
    home_lon: float | None = None
    preferred_remote_modes: frozenset[RemoteMode] = field(
        default_factory=lambda: frozenset({RemoteMode.REMOTE})
    )
    effective_salary_floor: float | None = None
    seniority_floor: int = 0
    qualification_gap_penalties: dict[str, float] = field(default_factory=dict)
    geo_weight_multiplier: float = 1.0
    right_swipe_count: int = 0
    blocked_companies: frozenset[str] = field(default_factory=frozenset)
    facet_exposure_counts: dict[str, int] = field(default_factory=dict)
    daily_weight_delta_used: float = 0.0
    daily_weight_delta_date: str | None = None


@dataclass(frozen=True)
class JobFeatures:
    job_id: str
    title: str
    company_id: str
    company_name: str
    normalized_title: str = ""
    embedding: tuple[float, ...] | None = None
    skills: frozenset[str] = field(default_factory=frozenset)
    salary_min: float | None = None
    salary_max: float | None = None
    seniority_level: int = 2
    seniority_known: bool = False
    remote_mode: RemoteMode = RemoteMode.UNKNOWN
    industry: str | None = None
    job_family: str | None = None
    stack_tags: frozenset[str] = field(default_factory=frozenset)
    company_size: str | None = None
    lat: float | None = None
    lon: float | None = None
    is_closed: bool = False
    age_days: float = 0.0
    date_posted: date | None = None
    popularity_score: float = 0.0
    requires_work_authorization: bool = False
    country: str | None = None
    location_text: str | None = None
    commute_minutes: int | None = None
    facet_values: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ScoredJob:
    job: JobFeatures
    score: float
    slot_type: str = "core"
    components: dict[str, float] = field(default_factory=dict)


@dataclass
class SessionState:
    same_direction_streak: int = 0
    last_direction: str | None = None
    employer_counts_today: dict[str, int] = field(default_factory=dict)


@dataclass
class PreferenceState:
    profile: UserProfile
    session: SessionState = field(default_factory=SessionState)
    taste_positive_sum: list[float] = field(default_factory=list)
    taste_positive_weight: float = 0.0
    taste_negative_sum: list[float] = field(default_factory=list)
    taste_negative_weight: float = 0.0
    feedback_history: list[FeedbackEvent] = field(default_factory=list)


@dataclass(frozen=True)
class FeedbackEvent:
    user_id: str
    job_id: str
    action: FeedbackAction
    timestamp: datetime
    job: JobFeatures
    reason: RejectionReason | None = None
    dwell_seconds: float | None = None


def facet_key(category: str, value: str) -> str:
    return f"{category}:{value}"


def effective_hard_constraints(profile: UserProfile, base: HardConstraints) -> HardConstraints:
    """Merge profile-level blocklist into hard constraints."""
    blocked = frozenset(base.blocked_companies | profile.blocked_companies)
    return HardConstraints(
        min_salary=base.min_salary,
        allowed_remote_modes=base.allowed_remote_modes,
        home_lat=base.home_lat if base.home_lat is not None else profile.home_lat,
        home_lon=base.home_lon if base.home_lon is not None else profile.home_lon,
        max_commute_radius_miles=base.max_commute_radius_miles,
        max_commute_minutes=base.max_commute_minutes,
        remote_openness=base.remote_openness,
        blocked_industries=base.blocked_industries,
        requires_work_authorization=base.requires_work_authorization,
        user_has_work_authorization=base.user_has_work_authorization,
        blocked_companies=blocked,
    )


def job_facet_map(job: JobFeatures) -> dict[str, str]:
    facets: dict[str, str] = dict(job.facet_values)
    if job.job_family:
        facets.setdefault("job_family", job.job_family)
    if job.industry:
        facets.setdefault("industry", job.industry)
    if job.company_size:
        facets.setdefault("company_size", job.company_size)
    facets.setdefault("remote_mode", job.remote_mode.value)
    for tag in job.stack_tags:
        facets.setdefault(f"stack:{tag}", tag)
    facets.setdefault("company", job.company_id)
    return facets
