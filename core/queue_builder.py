"""Queue builder: signup backfill, nightly top-up, and expiry hygiene (plan §5, E2.8)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from core.constraints import filter_hard_constraints
from core.deck_ranking import apply_deck_eligibility, enrich_scored_job, sort_deck_jobs
from core.geo.commute import enrich_commute_minutes
from core.job_retention import open_corpus_filter
from core.models import (
    Event,
    EventType,
    FeedbackAction,
    FeedbackEvent,
    Job,
    JobStatus,
    PreferenceWeights,
    Profile,
    QueueSlotType,
    QueueState,
    UserJobQueue,
)
from core.models import (
    HardConstraints as HardConstraintsRow,
)
from core.models import (
    ScoringConfig as ScoringConfigRow,
)
from core.preference import apply_per_employer_cap
from core.preference import select_explore_jobs as preference_select_explore
from core.profile_loader import user_profile_from_orm
from core.scoring import passes_core_relevance, score_jobs
from core.scoring_config_loader import scoring_config_from_db_rows
from core.seniority import seniority_to_int
from core.types import (
    HardConstraints,
    JobFeatures,
    RemoteMode,
    RemoteOpenness,
    ScoredJob,
    ScoringConfig,
    SessionState,
    UserProfile,
    effective_hard_constraints,
    job_facet_map,
)

CORPUS_WINDOW_DAYS = 30
BACKFILL_WINDOW_PREFERRED_DAYS = 30
BACKFILL_WINDOW_MAX_DAYS = 30
QUEUE_EXPIRY_DAYS = 60
DEFAULT_DAILY_TOPUP_CAP = 30
EXPLORE_INTERVAL = 10
BACKFILL_FLUSH_SIZE = 20
CORPUS_SCORE_BATCH_SIZE = 150


@dataclass(frozen=True)
class QueueItemSnapshot:
    """Minimal queue row + job snapshot for pure expiry logic."""

    queue_id: str
    job_id: str
    state: str
    job: JobFeatures


@dataclass(frozen=True)
class BackfillResult:
    user_id: str
    enqueued: list[ScoredJob]
    skipped_existing: int


@dataclass(frozen=True)
class TopUpResult:
    user_id: str
    enqueued: list[ScoredJob]
    capped_count: int


@dataclass(frozen=True)
class ExpiryResult:
    expired_count: int
    expired_queue_ids: list[str]


def _utc_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(tz=UTC)
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now.astimezone(UTC)


def _days_between(start: date | datetime, end: datetime) -> float:
    if isinstance(start, datetime):
        start = start.date()
    return float((end.date() - start).days)


def job_age_days(
    job: JobFeatures,
    *,
    now: datetime | None = None,
    reference: date | datetime | None = None,
) -> float:
    """Age in days; prefer explicit age_days, else compute from reference date."""
    if job.age_days > 0:
        return job.age_days
    if reference is None:
        return job.age_days
    return _days_between(reference, _utc_now(now))


def is_job_expired(
    job: JobFeatures,
    *,
    expiry_days: int = QUEUE_EXPIRY_DAYS,
    now: datetime | None = None,
    reference: date | datetime | None = None,
) -> bool:
    """True when the job is closed or older than the queue expiry window."""
    if job.is_closed:
        return True
    age = job_age_days(job, now=now, reference=reference)
    return age > expiry_days


def within_backfill_window(
    job: JobFeatures,
    *,
    window_days: int = BACKFILL_WINDOW_MAX_DAYS,
    now: datetime | None = None,
    first_seen: datetime | None = None,
) -> bool:
    """Corpus jobs eligible for signup backfill (trailing window)."""
    if job.is_closed:
        return False
    if first_seen is not None:
        age = _days_between(first_seen, _utc_now(now))
        return age <= window_days
    return job.age_days <= window_days


def sort_by_score_desc(jobs: list[ScoredJob]) -> list[ScoredJob]:
    return sorted(jobs, key=lambda item: (-item.score, item.job.job_id))


def _apply_score_floors(
    ranked: list[ScoredJob],
    config: ScoringConfig,
) -> list[ScoredJob]:
    """Drop jobs below explore floor; core-only callers filter again at 0.35."""
    return [item for item in ranked if item.score >= config.min_explore_score]


def _apply_core_score_floor(
    jobs: list[ScoredJob],
    config: ScoringConfig,
) -> list[ScoredJob]:
    return [
        item
        for item in jobs
        if item.score >= config.min_match_score and passes_core_relevance(item, config)
    ]


def apply_daily_cap(jobs: list[ScoredJob], cap: int) -> tuple[list[ScoredJob], int]:
    """Return at most ``cap`` jobs and the number dropped by the cap."""
    if cap <= 0:
        return [], len(jobs)
    if len(jobs) <= cap:
        return jobs, 0
    return jobs[:cap], len(jobs) - cap


def _primary_facet(job: ScoredJob) -> str:
    facets = job_facet_map(job.job)
    return facets.get("job_family") or facets.get("industry") or "unknown"


def select_explore_jobs(
    ranked: list[ScoredJob],
    facet_exposure: dict[str, int],
    *,
    explore_ratio: float = 0.10,
) -> tuple[list[ScoredJob], list[ScoredJob]]:
    """Split ranked jobs into core and explore pools (plan §10 exploration slot)."""
    if not ranked:
        return [], []

    target_explore = max(1, round(len(ranked) * explore_ratio)) if explore_ratio > 0 else 0
    if target_explore == 0:
        return ranked, []

    scores = sorted(job.score for job in ranked)
    median_score = scores[len(scores) // 2]
    min_exposure = min(facet_exposure.values(), default=0)

    explore: list[ScoredJob] = []
    explore_ids: set[str] = set()
    for job in ranked:
        if len(explore) >= target_explore:
            break
        facet = _primary_facet(job)
        exposure = facet_exposure.get(facet, 0)
        if job.score >= median_score and exposure <= min_exposure + 2:
            explore.append(job)
            explore_ids.add(job.job.job_id)

    core = [job for job in ranked if job.job.job_id not in explore_ids]
    return core, explore


def interleave_explore(
    core: list[ScoredJob],
    explore: list[ScoredJob],
    *,
    interval: int = EXPLORE_INTERVAL,
) -> list[ScoredJob]:
    """Insert explore picks roughly every ``interval`` cards (default ~1 in 10)."""
    if interval <= 0:
        return [replace(job, slot_type="core") for job in core] + [
            replace(job, slot_type="explore") for job in explore
        ]

    result: list[ScoredJob] = []
    core_idx = 0
    explore_idx = 0
    position = 1

    while core_idx < len(core) or explore_idx < len(explore):
        use_explore = position % interval == 0 and explore_idx < len(explore)
        if use_explore:
            job = explore[explore_idx]
            explore_idx += 1
            result.append(replace(job, slot_type="explore"))
        elif core_idx < len(core):
            job = core[core_idx]
            core_idx += 1
            result.append(replace(job, slot_type="core"))
        elif explore_idx < len(explore):
            job = explore[explore_idx]
            explore_idx += 1
            result.append(replace(job, slot_type="explore"))
        else:
            break
        position += 1

    return result


def build_backfill_deck(
    scored_jobs: list[ScoredJob],
    *,
    excluded_job_ids: set[str],
    constraints: HardConstraints,
    profile: UserProfile | None = None,
    facet_exposure: dict[str, int] | None = None,
    config: ScoringConfig | None = None,
    window_days: int = BACKFILL_WINDOW_MAX_DAYS,
    now: datetime | None = None,
    first_seen_by_job: dict[str, datetime] | None = None,
    employer_counts: dict[str, int] | None = None,
) -> list[ScoredJob]:
    """Pure backfill: filter → score order → explore interleave → employer cap → deck cap."""
    cfg = config or ScoringConfig()
    _ = facet_exposure

    eligible: list[ScoredJob] = []
    for item in scored_jobs:
        job = item.job
        if job.job_id in excluded_job_ids:
            continue
        first_seen = (first_seen_by_job or {}).get(job.job_id)
        if not within_backfill_window(
            job, window_days=window_days, now=now, first_seen=first_seen
        ):
            continue
        eligible.append(item)

    filtered_jobs = [item.job for item in eligible]
    passing_ids = {job.job_id for job in filter_hard_constraints(filtered_jobs, constraints)}
    passing = [item for item in eligible if item.job.job_id in passing_ids]

    if profile is not None:
        passing = [enrich_scored_job(item, profile) for item in passing]
        ranked = sort_deck_jobs(passing)
    else:
        ranked = sort_by_score_desc(passing)
    explore_count = max(1, round(len(ranked) * cfg.explore_slot_ratio)) if ranked else 0

    if profile is not None and explore_count > 0:
        explore_raw = preference_select_explore(ranked, profile, cfg, explore_count)
        explore_ids = {item.job.job_id for item in explore_raw}
        explore = [replace(item, slot_type="explore") for item in explore_raw]
        core_candidates = [
            replace(item, slot_type="core") for item in ranked if item.job.job_id not in explore_ids
        ]
        core = _apply_core_score_floor(core_candidates, cfg)
        core = apply_deck_eligibility(core, profile, config=cfg)
    elif profile is not None:
        core = apply_deck_eligibility(
            _apply_core_score_floor([replace(item, slot_type="core") for item in ranked], cfg),
            profile,
            config=cfg,
        )
        explore = []
    else:
        ranked = _apply_score_floors(ranked, cfg)
        core, explore = select_explore_jobs(ranked, facet_exposure or {}, explore_ratio=cfg.explore_slot_ratio)
        core = _apply_core_score_floor([replace(item, slot_type="core") for item in core], cfg)
        explore = [replace(item, slot_type="explore") for item in explore]

    deck = (
        interleave_explore(
            core, explore, interval=max(1, round(1 / cfg.explore_slot_ratio))
        )
        if cfg.explore_slot_ratio > 0
        else core
    )
    session = SessionState(employer_counts_today=dict(employer_counts or {}))
    deck = apply_per_employer_cap(
        deck,
        session,
        cfg,
        limit=cfg.backfill_max_jobs_per_employer,
    )
    capped, _ = apply_daily_cap(deck, cfg.backfill_deck_cap)
    return capped


def choose_backfill_window_days(
    scored_jobs: list[ScoredJob],
    *,
    excluded_job_ids: set[str],
    constraints: HardConstraints,
    profile: UserProfile | None = None,
    facet_exposure: dict[str, int] | None = None,
    config: ScoringConfig | None = None,
    now: datetime | None = None,
    first_seen_by_job: dict[str, datetime] | None = None,
    employer_counts: dict[str, int] | None = None,
) -> int:
    """Prefer a 30-day training window when it can fill the initial deck cap."""
    cfg = config or ScoringConfig()
    deck_preferred = build_backfill_deck(
        scored_jobs,
        excluded_job_ids=excluded_job_ids,
        constraints=constraints,
        profile=profile,
        facet_exposure=facet_exposure,
        config=cfg,
        window_days=BACKFILL_WINDOW_PREFERRED_DAYS,
        now=now,
        first_seen_by_job=first_seen_by_job,
        employer_counts=employer_counts,
    )
    if len(deck_preferred) >= cfg.backfill_deck_cap:
        return BACKFILL_WINDOW_PREFERRED_DAYS
    return BACKFILL_WINDOW_MAX_DAYS


def build_topup_deck(
    scored_jobs: list[ScoredJob],
    *,
    excluded_job_ids: set[str],
    constraints: HardConstraints,
    config: ScoringConfig | None = None,
    employer_counts: dict[str, int] | None = None,
) -> tuple[list[ScoredJob], int]:
    """Pure nightly top-up: filter, score order, employer cap, apply daily cap."""
    cfg = config or ScoringConfig()

    eligible = [
        item
        for item in scored_jobs
        if item.job.job_id not in excluded_job_ids and not item.job.is_closed
    ]
    filtered_jobs = [item.job for item in eligible]
    passing_ids = {job.job_id for job in filter_hard_constraints(filtered_jobs, constraints)}
    passing = [item for item in eligible if item.job.job_id in passing_ids]

    ranked = _apply_core_score_floor(sort_by_score_desc(passing), cfg)
    session = SessionState(employer_counts_today=dict(employer_counts or {}))
    ranked = apply_per_employer_cap(ranked, session, cfg)
    capped, dropped = apply_daily_cap(ranked, cfg.daily_topup_cap)
    return [replace(job, slot_type="core") for job in capped], dropped


def find_expirable_items(
    items: list[QueueItemSnapshot],
    *,
    expiry_days: int = QUEUE_EXPIRY_DAYS,
    now: datetime | None = None,
    reference_by_job: dict[str, date | datetime] | None = None,
) -> list[str]:
    """Return queue row ids that should move to expired_unswiped."""
    expired: list[str] = []
    for item in items:
        if item.state != QueueState.QUEUED.value:
            continue
        reference = (reference_by_job or {}).get(item.job_id)
        if is_job_expired(
            item.job,
            expiry_days=expiry_days,
            now=now,
            reference=reference,
        ):
            expired.append(item.queue_id)
    return expired


def job_features_from_orm(job: Job, *, now: datetime | None = None) -> JobFeatures:
    """Map a Job ORM row to JobFeatures for constraint filtering and expiry."""
    now = _utc_now(now)
    age = _days_between(job.first_seen, now) if job.first_seen is not None else 0.0
    remote = RemoteMode(job.remote_mode.value if hasattr(job.remote_mode, "value") else job.remote_mode)
    embedding = tuple(job.embedding) if job.embedding is not None else None

    company = job.company if hasattr(job, "company") else None
    industry = company.industry if company is not None else None
    company_size = company.size_band if company is not None else None

    raw = job.raw or {}
    job_family = raw.get("job_family") or job.normalized_title or None
    requires_auth = bool(raw.get("requires_work_authorization", False))
    popularity = float(raw.get("popularity_score") or 0.0)

    skills = frozenset(s.lower() for s in (job.skills or []))

    return JobFeatures(
        job_id=str(job.id),
        title=job.title,
        normalized_title=job.normalized_title or job.title,
        company_id=str(job.company_id) if job.company_id else job.company_name,
        company_name=job.company_name,
        embedding=embedding,
        skills=skills,
        salary_min=float(job.salary_min) if job.salary_min is not None else None,
        salary_max=float(job.salary_max) if job.salary_max is not None else None,
        seniority_level=seniority_to_int(job.seniority_int if job.seniority_int is not None else job.seniority_level),
        seniority_known=(
            job.seniority_int is not None
            or (job.seniority_level is not None and str(job.seniority_level).strip() != "")
        ),
        remote_mode=remote,
        industry=industry,
        job_family=str(job_family) if job_family else None,
        stack_tags=skills,
        company_size=company_size,
        lat=job.latitude,
        lon=job.longitude,
        is_closed=job.status == JobStatus.CLOSED,
        age_days=age,
        date_posted=job.date_posted,
        popularity_score=popularity,
        requires_work_authorization=requires_auth,
        country=job.country,
        location_text=job.location_text,
        facet_values={
            "remote_mode": remote.value,
            "primary_source": job.primary_source or "",
        },
    )


def hard_constraints_from_orm(row: HardConstraintsRow) -> HardConstraints:
    """Map hard_constraints table row to domain HardConstraints."""
    remote_modes: set[RemoteMode] = set()
    if row.remote_acceptability:
        for mode, allowed in row.remote_acceptability.items():
            if allowed:
                try:
                    remote_modes.add(RemoteMode(mode))
                except ValueError:
                    remote_modes.add(RemoteMode.UNKNOWN)
    if not remote_modes:
        remote_modes = {
            RemoteMode.REMOTE,
            RemoteMode.HYBRID,
            RemoteMode.ONSITE,
            RemoteMode.UNKNOWN,
        }

    home_lat = None
    home_lon = None
    if row.locations:
        first = row.locations[0]
        home_lat = first.get("lat")
        home_lon = first.get("lon")

    return HardConstraints(
        min_salary=float(row.min_salary) if row.min_salary is not None else None,
        allowed_remote_modes=frozenset(remote_modes),
        home_lat=float(home_lat) if home_lat is not None else None,
        home_lon=float(home_lon) if home_lon is not None else None,
        max_commute_radius_miles=float(row.location_radius_miles)
        if row.location_radius_miles is not None
        else None,
        max_commute_minutes=row.max_commute_minutes,
        remote_openness=_parse_remote_openness(row.remote_openness),
        blocked_industries=frozenset(row.never_industries or []),
        blocked_companies=frozenset(row.blocked_companies or []),
    )


def _parse_remote_openness(value: str | None) -> RemoteOpenness:
    if not value:
        return RemoteOpenness.OPEN_TO_REMOTE
    try:
        return RemoteOpenness(value)
    except ValueError:
        return RemoteOpenness.OPEN_TO_REMOTE


def scoring_config_from_db(rows: list[ScoringConfigRow]) -> ScoringConfig:
    """Load ScoringConfig dataclass from scoring_config key/value rows."""
    return scoring_config_from_db_rows(rows)


class QueueBuilderStore(Protocol):
    """Abstract persistence for queue builder I/O (enables unit tests without DB)."""

    def load_scoring_config(self) -> ScoringConfig: ...

    def load_user_profile(self, user_id: uuid.UUID) -> UserProfile | None: ...

    def employer_counts_today(self, user_id: uuid.UUID) -> dict[str, int]: ...

    def load_user_constraints(self, user_id: uuid.UUID) -> HardConstraints: ...

    def load_facet_exposure(self, user_id: uuid.UUID) -> dict[str, int]: ...

    def existing_queue_job_ids(self, user_id: uuid.UUID) -> set[str]: ...

    def load_corpus_scored_jobs(
        self, user_id: uuid.UUID, *, window_days: int
    ) -> list[ScoredJob]: ...

    def iter_corpus_job_batches(
        self, user_id: uuid.UUID, *, window_days: int, batch_size: int
    ) -> Iterator[list[Job]]: ...

    def score_job_rows(self, user_id: uuid.UUID, jobs: list[Job]) -> list[ScoredJob]: ...

    def load_today_scored_jobs(self, user_id: uuid.UUID, *, day: date) -> list[ScoredJob]: ...

    def load_daily_topup_cap(self, user_id: uuid.UUID) -> int: ...

    def enqueue_jobs(self, user_id: uuid.UUID, jobs: list[ScoredJob]) -> int: ...

    def list_queued_items(self) -> list[QueueItemSnapshot]: ...

    def mark_expired(self, queue_ids: list[str]) -> int: ...

    def record_event(
        self,
        user_id: uuid.UUID | None,
        event_type: str,
        payload: dict[str, Any],
    ) -> None: ...


class SqlAlchemyQueueBuilderStore:
    """SQLAlchemy-backed QueueBuilderStore."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def load_scoring_config(self) -> ScoringConfig:
        from dataclasses import replace

        from core.batch_jobs import corpus_skill_coverage

        rows = self._session.scalars(select(ScoringConfigRow)).all()
        if not rows:
            config = ScoringConfig(daily_topup_cap=DEFAULT_DAILY_TOPUP_CAP)
        else:
            config = scoring_config_from_db(list(rows))
        coverage = corpus_skill_coverage(self._session)
        return replace(config, skill_coverage_ratio=coverage)

    def load_user_profile(self, user_id: uuid.UUID) -> UserProfile | None:
        return self._load_user_profile(user_id)

    def employer_counts_today(self, user_id: uuid.UUID) -> dict[str, int]:
        today = _utc_now().date()
        start = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        rows = self._session.scalars(
            select(UserJobQueue)
            .where(UserJobQueue.user_id == user_id)
            .where(UserJobQueue.created_at >= start)
        ).all()
        counts: dict[str, int] = {}
        for item in rows:
            job = item.job
            if job is None:
                continue
            employer = str(job.company_id) if job.company_id else job.company_name
            counts[employer] = counts.get(employer, 0) + 1
        return counts

    def load_user_constraints(self, user_id: uuid.UUID) -> HardConstraints:
        row = self._session.scalar(
            select(HardConstraintsRow).where(HardConstraintsRow.user_id == user_id)
        )
        if row is None:
            return HardConstraints()
        return hard_constraints_from_orm(row)

    def load_facet_exposure(self, user_id: uuid.UUID) -> dict[str, int]:
        rows = self._session.scalars(
            select(UserJobQueue)
            .where(UserJobQueue.user_id == user_id)
            .where(UserJobQueue.state != QueueState.EXPIRED.value)
        ).all()
        exposure: dict[str, int] = {}
        for item in rows:
            job = item.job
            if job is None:
                continue
            features = job_features_from_orm(job)
            facet = job_facet_map(features).get("job_family", "unknown")
            exposure[facet] = exposure.get(facet, 0) + 1
        return exposure

    def existing_queue_job_ids(self, user_id: uuid.UUID) -> set[str]:
        rows = self._session.scalars(
            select(UserJobQueue.job_id).where(UserJobQueue.user_id == user_id)
        ).all()
        return {str(job_id) for job_id in rows}

    def _load_user_profile(self, user_id: uuid.UUID) -> UserProfile | None:
        profile = self._session.scalar(
            select(Profile).where(Profile.user_id == user_id)
        )
        if profile is None or profile.onboarding_completed_at is None:
            return None
        weights = self._session.scalar(
            select(PreferenceWeights)
            .where(PreferenceWeights.user_id == user_id)
            .where(PreferenceWeights.is_current.is_(True))
        )
        constraints_row = self._session.scalar(
            select(HardConstraintsRow).where(HardConstraintsRow.user_id == user_id)
        )
        return user_profile_from_orm(profile, weights, hard_constraints=constraints_row)

    def _score_jobs_for_user(self, user_id: uuid.UUID, jobs: list[Job]) -> list[ScoredJob]:
        profile = self._load_user_profile(user_id)
        if profile is None:
            return [ScoredJob(job=job_features_from_orm(job), score=0.0) for job in jobs]
        config = self.load_scoring_config()
        base_constraints = self.load_user_constraints(user_id)
        constraints = effective_hard_constraints(profile, base_constraints)
        features = [job_features_from_orm(job) for job in jobs]
        features = enrich_commute_minutes(self._session, constraints, features)
        return score_jobs(profile, features, config, constraints)

    def _open_jobs_query(self, *, cutoff: datetime | None = None) -> Any:
        stmt = (
            select(Job)
            .options(joinedload(Job.company))
            .where(Job.status == JobStatus.OPEN.value)
            .where(open_corpus_filter())
        )
        if cutoff is not None:
            stmt = stmt.where(Job.first_seen >= cutoff)
        return stmt

    def load_corpus_scored_jobs(
        self, user_id: uuid.UUID, *, window_days: int
    ) -> list[ScoredJob]:
        cutoff = _utc_now() - timedelta(days=window_days)
        rows = self._session.scalars(self._open_jobs_query(cutoff=cutoff)).unique().all()
        return self._score_jobs_for_user(user_id, list(rows))

    def iter_corpus_job_batches(
        self,
        user_id: uuid.UUID,
        *,
        window_days: int,
        batch_size: int = CORPUS_SCORE_BATCH_SIZE,
    ) -> Iterator[list[Job]]:
        _ = user_id
        cutoff = _utc_now() - timedelta(days=window_days)
        offset = 0
        while True:
            rows = self._session.scalars(
                self._open_jobs_query(cutoff=cutoff)
                .order_by(Job.id)
                .offset(offset)
                .limit(batch_size)
            ).unique().all()
            if not rows:
                break
            yield list(rows)
            offset += len(rows)
            if len(rows) < batch_size:
                break

    def score_job_rows(self, user_id: uuid.UUID, jobs: list[Job]) -> list[ScoredJob]:
        return self._score_jobs_for_user(user_id, jobs)

    def load_today_scored_jobs(self, user_id: uuid.UUID, *, day: date) -> list[ScoredJob]:
        start = datetime.combine(day, datetime.min.time(), tzinfo=UTC)
        end = start + timedelta(days=1)
        rows = self._session.scalars(
            self._open_jobs_query(cutoff=start)
            .where(Job.first_seen < end)
        ).unique().all()
        return self._score_jobs_for_user(user_id, list(rows))

    def load_daily_topup_cap(self, user_id: uuid.UUID) -> int:
        from core.entitlements import default_entitlements, entitlements_for_user
        from core.models import User

        user = self._session.get(User, user_id)
        if user is None:
            return default_entitlements().daily_topup_cap or 10_000
        cap = entitlements_for_user(user).daily_topup_cap
        return cap if cap is not None else 10_000

    def enqueue_jobs(self, user_id: uuid.UUID, jobs: list[ScoredJob]) -> int:
        from inference.explanations import template_explanation

        profile = self._load_user_profile(user_id)
        user_dict: dict[str, object] = {}
        if profile is not None:
            user_dict = {
                "skills": list(profile.skills),
                "target_salary": profile.target_salary,
                "seniority_level": profile.seniority_level,
                "remote_preference": next(iter(profile.preferred_remote_modes)).value
                if profile.preferred_remote_modes
                else "remote",
            }

        count = 0
        for item in jobs:
            slot = QueueSlotType.CORE if item.slot_type == "core" else QueueSlotType.EXPLORE
            job_row = self._session.get(Job, uuid.UUID(item.job.job_id))
            explain = None
            if job_row is not None:
                job_dict = {
                    "title": job_row.title,
                    "company": job_row.company_name,
                    "skills": list(job_row.skills or []),
                    "salary_min": job_row.salary_min,
                    "salary_max": job_row.salary_max,
                    "seniority_level": job_row.seniority_level,
                    "remote_mode": job_row.remote_mode.value
                    if hasattr(job_row.remote_mode, "value")
                    else job_row.remote_mode,
                }
                bullets = template_explanation(
                    user_profile=user_dict,
                    job=job_dict,
                    score_features=item.components,
                )
                explain = {
                    "why_bullets": bullets.why,
                    "caution_bullets": bullets.caution,
                    "source": bullets.source,
                }
            stored_score = float(item.components.get("deck_rank_score", item.score))
            is_stretch = bool(item.components.get("stretch"))
            row = UserJobQueue(
                user_id=user_id,
                job_id=uuid.UUID(item.job.job_id),
                score=stored_score,
                score_components=dict(item.components),
                explain=explain,
                is_stretch=is_stretch,
                slot_type=slot.value,
                state=QueueState.QUEUED.value,
            )
            self._session.add(row)
            count += 1
        return count

    def list_queued_items(self) -> list[QueueItemSnapshot]:
        rows = self._session.scalars(
            select(UserJobQueue)
            .where(UserJobQueue.state == QueueState.QUEUED.value)
            .join(Job, UserJobQueue.job_id == Job.id)
        ).all()
        snapshots: list[QueueItemSnapshot] = []
        for row in rows:
            job = row.job
            if job is None:
                continue
            snapshots.append(
                QueueItemSnapshot(
                    queue_id=str(row.id),
                    job_id=str(row.job_id),
                    state=row.state,
                    job=job_features_from_orm(job),
                )
            )
        return snapshots

    def mark_expired(self, queue_ids: list[str]) -> int:
        if not queue_ids:
            return 0
        ids = [uuid.UUID(qid) for qid in queue_ids]
        rows = self._session.scalars(
            select(UserJobQueue).where(UserJobQueue.id.in_(ids))
        ).all()
        count = 0
        for row in rows:
            row.state = QueueState.EXPIRED
            self._session.add(
                FeedbackEvent(
                    user_id=row.user_id,
                    job_id=row.job_id,
                    action=FeedbackAction.EXPIRED_UNSWIPED.value,
                )
            )
            count += 1
        return count

    def record_event(
        self,
        user_id: uuid.UUID | None,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        self._session.add(
            Event(
                user_id=user_id,
                type=event_type,
                payload=payload,
            )
        )


class QueueBuilder:
    """Orchestrates backfill, top-up, and expiry using a QueueBuilderStore."""

    def __init__(self, store: QueueBuilderStore) -> None:
        self._store = store

    def backfill_user(
        self,
        user_id: uuid.UUID,
        *,
        now: datetime | None = None,
    ) -> BackfillResult:
        config = self._store.load_scoring_config()
        constraints = effective_hard_constraints(
            _empty_profile(str(user_id)),
            self._store.load_user_constraints(user_id),
        )
        excluded = self._store.existing_queue_job_ids(user_id)
        facet_exposure = self._store.load_facet_exposure(user_id)
        profile = self._store.load_user_profile(user_id)
        employer_counts = self._store.employer_counts_today(user_id)
        corpus = self._store.load_corpus_scored_jobs(
            user_id, window_days=CORPUS_WINDOW_DAYS
        )
        window_days = choose_backfill_window_days(
            corpus,
            excluded_job_ids=excluded,
            constraints=constraints,
            profile=profile,
            facet_exposure=facet_exposure,
            config=config,
            now=now,
            employer_counts=employer_counts,
        )

        deck = build_backfill_deck(
            corpus,
            excluded_job_ids=excluded,
            constraints=constraints,
            profile=profile,
            facet_exposure=facet_exposure,
            config=config,
            window_days=window_days,
            now=now,
            employer_counts=employer_counts,
        )

        if deck:
            self._store.enqueue_jobs(user_id, deck)
            self._store.record_event(
                user_id,
                EventType.QUEUE_BACKFILLED.value,
                {"count": len(deck), "user_id": str(user_id)},
            )

        return BackfillResult(
            user_id=str(user_id),
            enqueued=deck,
            skipped_existing=len(excluded),
        )

    def backfill_user_batched(
        self,
        user_id: uuid.UUID,
        *,
        flush_size: int = BACKFILL_FLUSH_SIZE,
        now: datetime | None = None,
    ) -> Iterator[int]:
        """Enqueue backfill deck in chunks; yield chunk sizes for incremental commits."""
        config = self._store.load_scoring_config()
        constraints = effective_hard_constraints(
            _empty_profile(str(user_id)),
            self._store.load_user_constraints(user_id),
        )
        excluded = self._store.existing_queue_job_ids(user_id)
        facet_exposure = self._store.load_facet_exposure(user_id)
        profile = self._store.load_user_profile(user_id)
        employer_counts = dict(self._store.employer_counts_today(user_id))

        accumulated: list[ScoredJob] = []
        enqueued_ids: set[str] = set()
        total = 0
        first_seen_by_job: dict[str, datetime] = {}
        chosen_window: int | None = None

        def build_args(*, window_days: int) -> dict[str, Any]:
            return {
                "excluded_job_ids": excluded | enqueued_ids,
                "constraints": constraints,
                "profile": profile,
                "facet_exposure": facet_exposure,
                "config": config,
                "window_days": window_days,
                "now": now,
                "first_seen_by_job": first_seen_by_job,
                "employer_counts": employer_counts,
            }

        def maybe_choose_window() -> None:
            nonlocal chosen_window
            if chosen_window is not None:
                return
            deck_30 = build_backfill_deck(
                accumulated,
                **build_args(window_days=BACKFILL_WINDOW_PREFERRED_DAYS),
            )
            if len(deck_30) >= config.backfill_deck_cap:
                chosen_window = BACKFILL_WINDOW_PREFERRED_DAYS

        def flush_pending() -> Iterator[int]:
            nonlocal total
            if chosen_window is None:
                return
            deck = build_backfill_deck(accumulated, **build_args(window_days=chosen_window))
            pending = [item for item in deck if item.job.job_id not in enqueued_ids]
            while len(pending) >= flush_size:
                chunk = pending[:flush_size]
                self._store.enqueue_jobs(user_id, chunk)
                for item in chunk:
                    employer = item.job.company_id
                    employer_counts[employer] = employer_counts.get(employer, 0) + 1
                enqueued_ids.update(item.job.job_id for item in chunk)
                total += len(chunk)
                yield len(chunk)
                pending = pending[flush_size:]

        for batch in self._store.iter_corpus_job_batches(
            user_id,
            window_days=CORPUS_WINDOW_DAYS,
            batch_size=CORPUS_SCORE_BATCH_SIZE,
        ):
            for job in batch:
                first_seen_by_job[str(job.id)] = job.first_seen
            accumulated.extend(self._store.score_job_rows(user_id, batch))
            maybe_choose_window()
            yield from flush_pending()

        if not accumulated:
            return

        if chosen_window is None:
            chosen_window = choose_backfill_window_days(
                accumulated,
                excluded_job_ids=excluded | enqueued_ids,
                constraints=constraints,
                profile=profile,
                facet_exposure=facet_exposure,
                config=config,
                now=now,
                first_seen_by_job=first_seen_by_job,
                employer_counts=employer_counts,
            )

        deck = build_backfill_deck(accumulated, **build_args(window_days=chosen_window))
        remaining = [item for item in deck if item.job.job_id not in enqueued_ids]
        for index in range(0, len(remaining), flush_size):
            chunk = remaining[index : index + flush_size]
            self._store.enqueue_jobs(user_id, chunk)
            for item in chunk:
                employer = item.job.company_id
                employer_counts[employer] = employer_counts.get(employer, 0) + 1
            enqueued_ids.update(item.job.job_id for item in chunk)
            total += len(chunk)
            yield len(chunk)

        if total:
            self._store.record_event(
                user_id,
                EventType.QUEUE_BACKFILLED.value,
                {"count": total, "user_id": str(user_id), "batched": True},
            )

    def topup_user(
        self,
        user_id: uuid.UUID,
        *,
        day: date | None = None,
    ) -> TopUpResult:
        from dataclasses import replace

        config = self._store.load_scoring_config()
        daily_cap = self._store.load_daily_topup_cap(user_id)
        config = replace(config, daily_topup_cap=daily_cap)
        constraints = effective_hard_constraints(
            _empty_profile(str(user_id)),
            self._store.load_user_constraints(user_id),
        )
        excluded = self._store.existing_queue_job_ids(user_id)
        employer_counts = self._store.employer_counts_today(user_id)
        today = day or _utc_now().date()
        candidates = self._store.load_today_scored_jobs(user_id, day=today)

        deck, dropped = build_topup_deck(
            candidates,
            excluded_job_ids=excluded,
            constraints=constraints,
            config=config,
            employer_counts=employer_counts,
        )

        if deck:
            self._store.enqueue_jobs(user_id, deck)
            self._store.record_event(
                user_id,
                EventType.QUEUE_TOPPED_UP.value,
                {"count": len(deck), "capped": dropped, "user_id": str(user_id)},
            )

        return TopUpResult(
            user_id=str(user_id),
            enqueued=deck,
            capped_count=dropped,
        )

    def expire_stale(self, *, now: datetime | None = None) -> ExpiryResult:
        items = self._store.list_queued_items()
        expired_ids = find_expirable_items(items, expiry_days=QUEUE_EXPIRY_DAYS, now=now)
        count = self._store.mark_expired(expired_ids)
        return ExpiryResult(expired_count=count, expired_queue_ids=expired_ids)


def _empty_profile(user_id: str) -> UserProfile:
    return UserProfile(user_id=user_id)
