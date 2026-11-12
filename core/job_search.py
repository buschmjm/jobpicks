"""Full-corpus job search with deck-aware ranking (Workstream F4)."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.sql import Select

from core.deck_ranking import enrich_scored_job
from core.job_retention import open_corpus_filter
from core.models import Company, Job, JobStatus
from core.models import ScoringConfig as ScoringConfigRow
from core.queue_builder import job_features_from_orm
from core.scoring import score_job
from core.scoring_config_loader import scoring_config_from_db_rows
from core.seniority import seniority_label
from core.types import HardConstraints, JobFeatures, ScoredJob, ScoringConfig, UserProfile, effective_hard_constraints


class JobSearchSort(StrEnum):
    RELEVANCE = "relevance"
    MATCH = "match"
    DATE = "date"
    SALARY = "salary"
    ATTAINABILITY = "attainability"


@dataclass(frozen=True)
class JobSearchFilters:
    remote_modes: frozenset[str] = frozenset()
    seniority_levels: frozenset[int] = frozenset()
    industries: frozenset[str] = frozenset()
    countries: frozenset[str] = frozenset()
    states: frozenset[str] = frozenset()
    sources: frozenset[str] = frozenset()
    employment_types: frozenset[str] = frozenset()
    min_salary: int | None = None
    posted_within_days: int | None = None
    direct_only: bool = False
    company: str | None = None
    include_reach: bool = True
    include_stretch: bool = True


@dataclass(frozen=True)
class SearchResult:
    job: JobFeatures
    match_score: float
    deck_rank_score: float
    attainability: float
    text_relevance: float
    search_score: float
    reach: bool
    stretch: bool
    components: dict[str, float]


@dataclass(frozen=True)
class FacetOption:
    value: str
    label: str
    count: int


@dataclass(frozen=True)
class JobSearchFacets:
    remote_modes: list[FacetOption]
    industries: list[FacetOption]
    countries: list[FacetOption]
    states: list[FacetOption]
    sources: list[FacetOption]
    employment_types: list[FacetOption]
    seniority_levels: list[FacetOption]


def _tokenize(query: str) -> list[str]:
    return [t for t in re.split(r"\W+", query.lower()) if len(t) >= 2]


def text_relevance_score(query: str, job: JobFeatures) -> float:
    tokens = _tokenize(query)
    if not tokens:
        return 0.0
    blob = f"{job.title} {job.normalized_title} {job.company_name}".lower()
    hits = sum(1 for token in tokens if token in blob)
    return hits / len(tokens)


def _normalize_relevance(scores: list[float]) -> list[float]:
    if not scores:
        return []
    max_score = max(scores)
    if max_score <= 0:
        return [0.0 for _ in scores]
    return [min(1.0, s / max_score) for s in scores]


def _is_stretch(profile: UserProfile, job: JobFeatures, match_score: float) -> bool:
    delta = job.seniority_level - profile.seniority_level
    return delta == 1 and match_score >= 0.55


def _open_jobs_stmt() -> Select[tuple[Job]]:
    return (
        select(Job)
        .options(joinedload(Job.company))
        .where(Job.status == JobStatus.OPEN.value)
        .where(open_corpus_filter())
    )


def _apply_db_filters(stmt: Select[tuple[Job]], filters: JobSearchFilters) -> Select[tuple[Job]]:
    if filters.remote_modes:
        stmt = stmt.where(Job.remote_mode.in_(sorted(filters.remote_modes)))
    if filters.countries:
        stmt = stmt.where(Job.country.in_(sorted(filters.countries)))
    if filters.states:
        stmt = stmt.where(Job.state.in_(sorted(filters.states)))
    if filters.sources:
        stmt = stmt.where(Job.primary_source.in_(sorted(filters.sources)))
    if filters.employment_types:
        stmt = stmt.where(Job.employment_type.in_(sorted(filters.employment_types)))
    if filters.direct_only:
        stmt = stmt.where(Job.is_direct.is_(True))
    if filters.min_salary is not None:
        stmt = stmt.where(
            or_(
                Job.salary_max >= filters.min_salary,
                Job.salary_min >= filters.min_salary,
            )
        )
    if filters.posted_within_days is not None:
        cutoff = date.today() - timedelta(days=filters.posted_within_days)
        stmt = stmt.where(Job.date_posted.is_not(None), Job.date_posted >= cutoff)
    if filters.company:
        pattern = f"%{filters.company.strip()}%"
        stmt = stmt.where(Job.company_name.ilike(pattern))
    if filters.industries:
        stmt = stmt.join(Company, Job.company_id == Company.id).where(
            Company.industry.in_(sorted(filters.industries))
        )
    if filters.seniority_levels:
        stmt = stmt.where(Job.seniority_int.in_(sorted(filters.seniority_levels)))
    return stmt


def _sort_results(results: list[SearchResult], sort: JobSearchSort) -> list[SearchResult]:
    if sort == JobSearchSort.MATCH:
        return sorted(
            results,
            key=lambda item: (
                -item.match_score,
                -(item.job.date_posted.toordinal() if item.job.date_posted else 0),
                item.job.job_id,
            ),
        )
    if sort == JobSearchSort.DATE:
        return sorted(
            results,
            key=lambda item: (
                -(item.job.date_posted.toordinal() if item.job.date_posted else 0),
                -item.search_score,
                item.job.job_id,
            ),
        )
    if sort == JobSearchSort.SALARY:
        return sorted(
            results,
            key=lambda item: (
                -(item.job.salary_max or item.job.salary_min or 0),
                -item.search_score,
                item.job.job_id,
            ),
        )
    if sort == JobSearchSort.ATTAINABILITY:
        return sorted(
            results,
            key=lambda item: (
                -item.attainability,
                -item.search_score,
                item.job.job_id,
            ),
        )
    return sorted(
        results,
        key=lambda item: (
            -item.search_score,
            -(item.job.date_posted.toordinal() if item.job.date_posted else 0),
            item.job.job_id,
        ),
    )


def search_jobs(
    session: Session,
    query: str,
    profile: UserProfile | None,
    *,
    constraints: HardConstraints | None = None,
    filters: JobSearchFilters | None = None,
    sort: JobSearchSort = JobSearchSort.RELEVANCE,
    limit: int = 50,
) -> list[SearchResult]:
    """
    Full search mode (S1/S2):
    - No attainability exclusions (reach flagged instead)
    - Rank: 0.7 * text_relevance + 0.3 * deck_rank_score (empty profile: deck term = 0.5)
    - attainability < 0.15 → reach:true; stretch per D2 logic
    """
    active_filters = filters or JobSearchFilters()
    tokens = _tokenize(query)
    stmt = _apply_db_filters(_open_jobs_stmt(), active_filters).limit(limit * 6)
    if tokens:
        clauses = []
        for token in tokens[:8]:
            pattern = f"%{token}%"
            clauses.append(
                or_(
                    Job.title.ilike(pattern),
                    Job.description.ilike(pattern),
                    Job.company_name.ilike(pattern),
                )
            )
        stmt = stmt.where(or_(*clauses))

    rows = list(session.scalars(stmt).unique().all())
    config_rows = session.scalars(select(ScoringConfigRow)).all()
    config = scoring_config_from_db_rows(list(config_rows)) if config_rows else ScoringConfig()

    raw_relevance: list[float] = []
    scored_items: list[tuple[JobFeatures, ScoredJob | None, float]] = []
    merged_constraints = (
        effective_hard_constraints(profile, constraints) if profile and constraints else constraints
    )

    for row in rows:
        features = job_features_from_orm(row, now=datetime.now(tz=UTC))
        rel = text_relevance_score(query, features)
        raw_relevance.append(rel)
        if profile is None:
            scored_items.append((features, None, rel))
            continue
        scored = score_job(profile, features, config, merged_constraints)
        scored_items.append((features, scored, rel))

    norm_relevance = _normalize_relevance(raw_relevance)
    results: list[SearchResult] = []

    for (features, scored, _), rel_norm in zip(scored_items, norm_relevance, strict=True):
        if profile is None:
            deck_term = 0.5
            match = 0.0
            att = 1.0
            components: dict[str, float] = {}
            stretch = False
        else:
            if scored is None:
                continue
            enriched = enrich_scored_job(scored, profile, session=session)
            match = float(enriched.components.get("match_score", enriched.score))
            att = float(enriched.components.get("attainability", 1.0))
            deck_term = float(enriched.components.get("deck_rank_score", enriched.score))
            components = dict(enriched.components)
            stretch = _is_stretch(profile, features, match)

        search_score = 0.7 * rel_norm + 0.3 * deck_term
        reach = att < 0.15
        if reach and not active_filters.include_reach:
            continue
        if stretch and not active_filters.include_stretch:
            continue
        results.append(
            SearchResult(
                job=features,
                match_score=match,
                deck_rank_score=deck_term,
                attainability=att,
                text_relevance=rel_norm,
                search_score=search_score,
                reach=reach,
                stretch=stretch,
                components=components,
            )
        )

    return _sort_results(results, sort)[:limit]


def _facet_rows(
    session: Session,
    column: Any,
    *,
    label_fn: Callable[[str], str] | None = None,
    limit: int = 40,
) -> list[FacetOption]:
    rows = session.execute(
        select(column, func.count())
        .select_from(Job)
        .where(Job.status == JobStatus.OPEN.value)
        .where(open_corpus_filter())
        .where(column.is_not(None))
        .where(column != "")
        .group_by(column)
        .order_by(func.count().desc(), column.asc())
        .limit(limit)
    ).all()
    options: list[FacetOption] = []
    for value, count in rows:
        raw = str(value)
        label = label_fn(raw) if label_fn else raw
        options.append(FacetOption(value=raw, label=label, count=int(count)))
    return options


def load_search_facets(session: Session) -> JobSearchFacets:
    seniority_rows = session.execute(
        select(Job.seniority_int, func.count())
        .where(Job.status == JobStatus.OPEN.value)
        .where(open_corpus_filter())
        .where(Job.seniority_int.is_not(None))
        .group_by(Job.seniority_int)
        .order_by(Job.seniority_int.asc())
    ).all()
    seniority_levels = [
        FacetOption(
            value=str(level),
            label=seniority_label(int(level)),
            count=int(count),
        )
        for level, count in seniority_rows
        if level is not None
    ]

    industry_rows = session.execute(
        select(Company.industry, func.count())
        .select_from(Job)
        .join(Company, Job.company_id == Company.id)
        .where(Job.status == JobStatus.OPEN.value)
        .where(open_corpus_filter())
        .where(Company.industry.is_not(None))
        .where(Company.industry != "")
        .group_by(Company.industry)
        .order_by(func.count().desc(), Company.industry.asc())
        .limit(40)
    ).all()
    industries = [
        FacetOption(value=str(value), label=str(value), count=int(count))
        for value, count in industry_rows
        if value
    ]

    return JobSearchFacets(
        remote_modes=_facet_rows(
            session,
            Job.remote_mode,
            label_fn=lambda value: value.replace("_", " ").title(),
        ),
        industries=industries,
        countries=_facet_rows(session, Job.country, label_fn=str.upper),
        states=_facet_rows(session, Job.state),
        sources=_facet_rows(session, Job.primary_source),
        employment_types=_facet_rows(
            session,
            Job.employment_type,
            label_fn=lambda value: value.replace("_", " ").title(),
        ),
        seniority_levels=seniority_levels,
    )
