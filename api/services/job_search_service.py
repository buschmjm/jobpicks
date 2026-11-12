"""Job search service (Workstream F4)."""

from __future__ import annotations

import uuid

from core.job_search import (
    FacetOption,
    JobSearchFilters,
    JobSearchSort,
    SearchResult,
    load_search_facets,
    search_jobs,
)
from core.models import HardConstraints as HardConstraintsRow
from core.models import Job, PreferenceWeights, Profile
from core.profile_loader import user_profile_from_orm
from core.queue_builder import hard_constraints_from_orm
from core.types import RemoteMode
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.schemas import JobSearchFacetOption, JobSearchFacetsResponse, JobSearchHit, JobSearchResponse


class JobSearchService:
    def facets(self, session: Session) -> JobSearchFacetsResponse:
        loaded = load_search_facets(session)
        return JobSearchFacetsResponse(
            remote_modes=[_facet_option(row) for row in loaded.remote_modes],
            industries=[_facet_option(row) for row in loaded.industries],
            countries=[_facet_option(row) for row in loaded.countries],
            states=[_facet_option(row) for row in loaded.states],
            sources=[_facet_option(row) for row in loaded.sources],
            employment_types=[_facet_option(row) for row in loaded.employment_types],
            seniority_levels=[_facet_option(row) for row in loaded.seniority_levels],
        )

    def search(
        self,
        session: Session,
        user_id: uuid.UUID,
        query: str,
        *,
        filters: JobSearchFilters | None = None,
        sort: JobSearchSort = JobSearchSort.RELEVANCE,
        limit: int = 50,
    ) -> JobSearchResponse:
        profile_row = session.scalar(select(Profile).where(Profile.user_id == user_id))
        weights = session.scalar(
            select(PreferenceWeights)
            .where(PreferenceWeights.user_id == user_id)
            .where(PreferenceWeights.is_current.is_(True))
        )
        constraints_row = session.scalar(
            select(HardConstraintsRow).where(HardConstraintsRow.user_id == user_id)
        )

        profile = None
        constraints = hard_constraints_from_orm(constraints_row) if constraints_row else None
        if profile_row is not None and profile_row.onboarding_completed_at is not None:
            profile = user_profile_from_orm(profile_row, weights, hard_constraints=constraints_row)

        results = search_jobs(
            session,
            query,
            profile,
            constraints=constraints,
            filters=filters,
            sort=sort,
            limit=limit,
        )
        job_ids = [uuid.UUID(hit.job.job_id) for hit in results]
        job_rows: dict[str, Job] = {}
        if job_ids:
            job_rows = {
                str(row.id): row for row in session.scalars(select(Job).where(Job.id.in_(job_ids))).all()
            }
        return JobSearchResponse(
            query=query,
            results=[_to_hit(row, job_rows.get(row.job.job_id)) for row in results],
            profile_complete=profile is not None,
            sort=sort.value,
        )


def _facet_option(row: FacetOption) -> JobSearchFacetOption:
    return JobSearchFacetOption(value=row.value, label=row.label, count=row.count)


def _format_salary(job: Job | None) -> str | None:
    if job is None:
        return None
    if job.salary_min is None and job.salary_max is None:
        return "salary not listed"
    if job.salary_min is not None and job.salary_max is not None:
        return f"${job.salary_min // 1000}–{job.salary_max // 1000}k"
    if job.salary_min is not None:
        return f"${job.salary_min // 1000}k+"
    assert job.salary_max is not None
    return f"up to ${job.salary_max // 1000}k"


def _location_display(job: Job | None) -> str | None:
    if job is None:
        return None
    parts = [part for part in (job.city, job.state, job.country) if part]
    if parts:
        return ", ".join(parts)
    return job.location_text


def _to_hit(row: SearchResult, job: Job | None) -> JobSearchHit:
    remote = row.job.remote_mode.value if isinstance(row.job.remote_mode, RemoteMode) else str(row.job.remote_mode)
    return JobSearchHit(
        job_id=uuid.UUID(row.job.job_id),
        title=row.job.title,
        company=row.job.company_name,
        match_score=round(row.match_score, 4),
        deck_rank_score=round(row.deck_rank_score, 4),
        search_score=round(row.search_score, 4),
        attainability=round(row.attainability, 4),
        text_relevance=round(row.text_relevance, 4),
        reach=row.reach,
        stretch=row.stretch,
        remote_mode=remote,
        location_display=_location_display(job),
        salary_display=_format_salary(job),
        industry=row.job.industry,
        date_posted=row.job.date_posted,
        source=job.primary_source if job is not None else None,
    )


job_search_service = JobSearchService()
