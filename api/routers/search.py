"""Full-corpus job search (Workstream F4)."""

from __future__ import annotations

from core.job_search import JobSearchFilters, JobSearchSort
from fastapi import APIRouter, Depends, Query

from api.deps import DbSession, get_current_user
from api.schemas import JobSearchFacetsResponse, JobSearchResponse, SessionUser
from api.services.job_search_service import job_search_service

router = APIRouter(prefix="/search", tags=["search"])


def _parse_filters(
    *,
    remote_mode: list[str] | None = None,
    seniority: list[int] | None = None,
    industry: list[str] | None = None,
    country: list[str] | None = None,
    state: list[str] | None = None,
    source: list[str] | None = None,
    employment_type: list[str] | None = None,
    min_salary: int | None = None,
    posted_within_days: int | None = None,
    direct_only: bool = False,
    company: str | None = None,
    include_reach: bool = True,
    include_stretch: bool = True,
) -> JobSearchFilters:
    return JobSearchFilters(
        remote_modes=frozenset(remote_mode or []),
        seniority_levels=frozenset(seniority or []),
        industries=frozenset(industry or []),
        countries=frozenset(country or []),
        states=frozenset(state or []),
        sources=frozenset(source or []),
        employment_types=frozenset(employment_type or []),
        min_salary=min_salary,
        posted_within_days=posted_within_days,
        direct_only=direct_only,
        company=(company or "").strip() or None,
        include_reach=include_reach,
        include_stretch=include_stretch,
    )


@router.get("/facets", response_model=JobSearchFacetsResponse)
def search_facets_endpoint(
    db: DbSession,
    _: SessionUser = Depends(get_current_user),
) -> JobSearchFacetsResponse:
    return job_search_service.facets(db)


@router.get("/jobs", response_model=JobSearchResponse)
def search_jobs_endpoint(
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
    q: str = Query(default="", max_length=200),
    sort: JobSearchSort = Query(default=JobSearchSort.RELEVANCE),
    limit: int = Query(default=50, ge=1, le=100),
    remote_mode: list[str] = Query(default=[]),
    seniority: list[int] = Query(default=[]),
    industry: list[str] = Query(default=[]),
    country: list[str] = Query(default=[]),
    state: list[str] = Query(default=[]),
    source: list[str] = Query(default=[]),
    employment_type: list[str] = Query(default=[]),
    min_salary: int | None = Query(default=None, ge=0),
    posted_within_days: int | None = Query(default=None, ge=1, le=365),
    direct_only: bool = Query(default=False),
    company: str | None = Query(default=None, max_length=200),
    include_reach: bool = Query(default=True),
    include_stretch: bool = Query(default=True),
) -> JobSearchResponse:
    filters = _parse_filters(
        remote_mode=remote_mode,
        seniority=seniority,
        industry=industry,
        country=country,
        state=state,
        source=source,
        employment_type=employment_type,
        min_salary=min_salary,
        posted_within_days=posted_within_days,
        direct_only=direct_only,
        company=company,
        include_reach=include_reach,
        include_stretch=include_stretch,
    )
    return job_search_service.search(
        db,
        user.id,
        q,
        filters=filters,
        sort=sort,
        limit=limit,
    )
