"""Ingest runner: pull from source adapters and persist jobs to Postgres."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import replace
from datetime import UTC, datetime

from core.apply.ats_detect import enrich_standard_job_apply
from core.database import SessionLocal
from core.job_description import prefer_description
from core.job_retention import close_expired_api_postings
from core.models import Job, JobSource, JobStatus, RemoteMode
from core.search_terms import mark_terms_fetched
from core.skill_directory import replace_job_skills
from sqlalchemy import select
from sqlalchemy.orm import Session

from ingest.adapters.adzuna import AdzunaAdapter
from ingest.adapters.greenhouse import GreenhouseAdapter
from ingest.adapters.jsearch import JSearchAdapter
from ingest.adapters.lever import LeverAdapter
from ingest.adapters.remotive import RemotiveAdapter
from ingest.adapters.usajobs import USAJobsAdapter
from ingest.base import FetchParams, SourceAdapter
from ingest.companies_loader import load_company_seeds
from ingest.country import (
    DEFAULT_INGEST_COUNTRY,
    is_us_job_record,
    parse_us_city_state,
    resolve_job_country,
)
from ingest.pipeline import IngestPipeline, SafetyNetFilter, normalize_text
from ingest.quota import QuotaTracker, default_quota_tracker
from ingest.schema import StandardJob, WorkArrangement
from ingest.sweep_config import NIGHTLY_MAX_DAYS_OLD, USAJOBS_MAX_PAGES, jsearch_enabled

logger = logging.getLogger(__name__)

MISSED_CRAWLS_BEFORE_CLOSE = 3


def _work_arrangement_to_remote_mode(work_arrangement: WorkArrangement) -> RemoteMode:
    mapping = {
        WorkArrangement.REMOTE: RemoteMode.REMOTE,
        WorkArrangement.HYBRID: RemoteMode.HYBRID,
        WorkArrangement.ONSITE: RemoteMode.ONSITE,
    }
    return mapping.get(work_arrangement, RemoteMode.UNKNOWN)


def _standard_job_to_orm_fields(job: StandardJob, *, now: datetime) -> dict[str, object]:
    salary_min = None
    salary_max = None
    salary_currency = None
    salary_period = None
    if job.salary is not None:
        salary_min = int(job.salary.min_amount) if job.salary.min_amount is not None else None
        salary_max = int(job.salary.max_amount) if job.salary.max_amount is not None else None
        salary_currency = job.salary.currency
        salary_period = job.salary.period

    skills = list(job.required_technologies) if job.required_technologies else None
    raw_payload = dict(job.raw_payload or {})
    if job.source_id:
        raw_payload["source_id"] = job.source_id
    raw_payload["missed_crawls"] = 0

    resolved_country = resolve_job_country(country=job.country, location=job.location)
    city, state = (
        parse_us_city_state(job.location)
        if resolved_country == DEFAULT_INGEST_COUNTRY
        else (None, None)
    )

    apply_url, ats_type, ats_metadata = enrich_standard_job_apply(
        source_url=job.source_url,
        apply_url=job.apply_url,
        ats_type=job.ats_type,
        ats_metadata=job.ats_metadata,
    )

    return {
        "company_name": job.company,
        "title": job.title,
        "normalized_title": normalize_text(job.title),
        "location_text": job.location,
        "city": city,
        "state": state,
        "country": resolved_country,
        "latitude": job.latitude,
        "longitude": job.longitude,
        "remote_mode": _work_arrangement_to_remote_mode(job.work_arrangement),
        "employment_type": job.employment_type.value,
        "salary_min": salary_min,
        "salary_max": salary_max,
        "salary_currency": salary_currency,
        "salary_period": salary_period,
        "date_posted": job.date_posted,
        "description": job.description,
        "requirements": job.requirements,
        "skills": skills,
        "seniority_level": job.seniority_level,
        "primary_source": job.source,
        "source_url": job.source_url,
        "apply_url": apply_url,
        "ats_type": ats_type,
        "ats_metadata": ats_metadata or {},
        "canonical_hash": job.canonical_hash or "",
        "raw": raw_payload,
        "last_seen": now,
        "status": JobStatus.OPEN,
    }


def persist_job(session: Session, job: StandardJob, *, now: datetime | None = None) -> tuple[Job, bool]:
    """Upsert a normalized job by canonical_hash."""
    seen_at = now or datetime.now(UTC)
    assert job.canonical_hash, "canonical_hash required before persist"

    existing = session.scalar(select(Job).where(Job.canonical_hash == job.canonical_hash))
    fields = _standard_job_to_orm_fields(job, now=seen_at)

    if existing is not None:
        for key, value in fields.items():
            if key == "status":
                continue
            if key == "description":
                merged = prefer_description(existing.description, str(value or ""))
                if merged is not None:
                    existing.description = merged
                continue
            setattr(existing, key, value)
        job_row = existing
        created = False
    else:
        job_row = Job(first_seen=seen_at, **fields)
        session.add(job_row)
        session.flush()
        created = True

    session.flush()
    skills = fields.get("skills")
    replace_job_skills(
        session,
        job_row.id,
        skills if isinstance(skills, list) else None,
    )

    if job.source_id:
        source = session.scalar(
            select(JobSource).where(
                JobSource.source_name == job.source,
                JobSource.external_id == job.source_id,
            )
        )
        if source is None:
            session.add(
                JobSource(
                    job_id=job_row.id,
                    source_name=job.source,
                    external_id=job.source_id,
                    source_url=job.source_url,
                    fetched_at=job.collected_timestamp,
                    raw=job.raw_payload,
                )
            )
        else:
            source.job_id = job_row.id
            source.source_url = job.source_url
            source.fetched_at = job.collected_timestamp
            source.raw = job.raw_payload

    return job_row, created


def build_tier1_adapters(quota: QuotaTracker, *, jsearch_max_pages: int = 3) -> list[SourceAdapter]:
    adapters: list[SourceAdapter] = []
    if os.environ.get("ADZUNA_APP_ID") and os.environ.get("ADZUNA_APP_KEY"):
        adapters.append(AdzunaAdapter(quota=quota))
    else:
        logger.warning("skipping adzuna adapter: ADZUNA_APP_ID/ADZUNA_APP_KEY not set")
    if jsearch_enabled() and os.environ.get("JSEARCH_API_KEY"):
        adapters.append(JSearchAdapter(quota=quota, max_pages=jsearch_max_pages))
    elif os.environ.get("JSEARCH_API_KEY"):
        logger.info("skipping jsearch adapter: JSEARCH_ENABLED is not true")
    else:
        logger.warning("skipping jsearch adapter: JSEARCH_API_KEY not set")
    adapters.append(RemotiveAdapter(quota=quota))
    return adapters


def build_tier2_adapters(quota: QuotaTracker) -> list[tuple[SourceAdapter, FetchParams]]:
    """One adapter instance + params per company board from seeds/companies.yaml."""
    pairs: list[tuple[SourceAdapter, FetchParams]] = []
    base_params = FetchParams(
        search_terms=(),
        salary_min=None,
        max_days_old=NIGHTLY_MAX_DAYS_OLD,
        results_per_page=100,
    )
    for seed in load_company_seeds():
        if seed.greenhouse:
            gh_adapter: SourceAdapter = GreenhouseAdapter(
                quota=quota,
                board_token=seed.greenhouse,
                company_name=seed.name,
            )
            params = replace(
                base_params,
                extra={"board_token": seed.greenhouse, "company_name": seed.name},
            )
            pairs.append((gh_adapter, params))
        if seed.lever:
            lv_adapter: SourceAdapter = LeverAdapter(
                quota=quota,
                site_slug=seed.lever,
                company_name=seed.name,
            )
            params = replace(
                base_params,
                extra={"site_slug": seed.lever, "company_name": seed.name},
            )
            pairs.append((lv_adapter, params))
    return pairs


def build_usajobs_fetches(quota: QuotaTracker) -> list[tuple[SourceAdapter, FetchParams]]:
    """USAJOBS nightly sweep pages (no keyword)."""
    if not os.environ.get("USAJOBS_API_KEY"):
        logger.warning("skipping usajobs adapter: USAJOBS_API_KEY not set")
        return []

    adapter: SourceAdapter = USAJobsAdapter(quota=quota)
    base_params = FetchParams(
        search_terms=(),
        salary_min=None,
        max_days_old=NIGHTLY_MAX_DAYS_OLD,
        results_per_page=100,
    )
    return [
        (adapter, replace(base_params, page=page))
        for page in range(1, USAJOBS_MAX_PAGES + 1)
    ]


def apply_freshness_lifecycle(session: Session, seen_hashes: set[str]) -> dict[str, int]:
    """Mark jobs absent from this crawl; close after 3 consecutive misses (plan §8)."""
    stats = {"updated": 0, "closed": 0}
    rows = session.scalars(select(Job).where(Job.status == JobStatus.OPEN.value)).all()
    for job in rows:
        raw = dict(job.raw or {})
        if job.canonical_hash in seen_hashes:
            raw["missed_crawls"] = 0
            job.raw = raw
            continue
        missed = int(raw.get("missed_crawls", 0)) + 1
        raw["missed_crawls"] = missed
        job.raw = raw
        stats["updated"] += 1
        if missed >= MISSED_CRAWLS_BEFORE_CLOSE:
            job.status = JobStatus.CLOSED
            stats["closed"] += 1
    session.flush()
    return stats


async def _fetch_adapter(
    adapter: SourceAdapter,
    params: FetchParams,
    pipeline: IngestPipeline,
) -> tuple[list[StandardJob], int]:
    async with adapter:
        result = await adapter.fetch(params)
    fetched = len(result.jobs)
    accepted = pipeline.process_batch(result.jobs)
    return accepted, fetched


async def _persist_jobs(
    session: Session,
    jobs: list[StandardJob],
    stats: dict[str, int],
    *,
    now: datetime,
) -> None:
    for std_job in jobs:
        stats["accepted"] += 1
        row, created = persist_job(session, std_job, now=now)
        if created:
            stats["created"] += 1
        else:
            stats["updated"] += 1
        _ = row


def close_non_us_open_jobs(session: Session) -> int:
    """Close open jobs that are clearly outside the US product scope."""
    closed = 0
    rows = session.scalars(select(Job).where(Job.status == JobStatus.OPEN.value)).all()
    for job in rows:
        if is_us_job_record(
            country=job.country,
            location=job.location_text,
            source=job.primary_source,
        ):
            continue
        job.status = JobStatus.CLOSED
        closed += 1
    if closed:
        session.flush()
    return closed


def _empty_stats() -> dict[str, int]:
    return {
        "fetched": 0,
        "accepted": 0,
        "created": 0,
        "updated": 0,
        "closed_stale": 0,
        "closed_non_us": 0,
        "closed_expired_postings": 0,
        "terms_fetched": 0,
    }


def _make_pipeline() -> IngestPipeline:
    return IngestPipeline(
        safety_net=SafetyNetFilter(
            salary_min=None,
            max_days_old=NIGHTLY_MAX_DAYS_OLD,
            us_only=True,
        ),
    )


async def _run_term_ingest(
    session: Session,
    terms: tuple[str, ...],
    *,
    stats: dict[str, int],
    pipeline: IngestPipeline,
    quota: QuotaTracker,
    now: datetime,
) -> None:
    """Title-based subset ingest for newly registered target titles."""
    base_params = FetchParams(
        search_terms=(),
        salary_min=None,
        max_days_old=NIGHTLY_MAX_DAYS_OLD,
        results_per_page=50,
        extra={"country": "us"},
    )
    for adapter in build_tier1_adapters(quota, jsearch_max_pages=1):
        for term in terms:
            term_params = replace(base_params, search_terms=(term,))
            try:
                jobs, fetched = await _fetch_adapter(adapter, term_params, pipeline)
            except Exception:
                logger.exception("adapter %s fetch failed for term=%r", adapter.source_name, term)
                continue
            stats["fetched"] += fetched
            await _persist_jobs(session, jobs, stats, now=now)


async def _run_nightly_sweep(
    session: Session,
    *,
    stats: dict[str, int],
    pipeline: IngestPipeline,
    quota: QuotaTracker,
    now: datetime,
) -> None:
    """Board/feed sweep without title filters."""
    base_params = FetchParams(
        search_terms=(),
        salary_min=None,
        max_days_old=NIGHTLY_MAX_DAYS_OLD,
        results_per_page=100,
    )

    remotive = RemotiveAdapter(quota=quota)
    try:
        jobs, fetched = await _fetch_adapter(remotive, base_params, pipeline)
    except Exception:
        logger.exception("adapter remotive fetch failed")
    else:
        stats["fetched"] += fetched
        await _persist_jobs(session, jobs, stats, now=now)

    for adapter, board_params in build_tier2_adapters(quota):
        try:
            jobs, fetched = await _fetch_adapter(adapter, board_params, pipeline)
        except Exception:
            logger.exception("adapter %s fetch failed", adapter.source_name)
            continue
        stats["fetched"] += fetched
        await _persist_jobs(session, jobs, stats, now=now)

    for adapter, page_params in build_usajobs_fetches(quota):
        try:
            jobs, fetched = await _fetch_adapter(adapter, page_params, pipeline)
        except Exception:
            logger.exception("adapter %s fetch failed page=%s", adapter.source_name, page_params.page)
            continue
        stats["fetched"] += fetched
        await _persist_jobs(session, jobs, stats, now=now)


async def pull_all_sources(
    session: Session,
    *,
    search_terms: tuple[str, ...] | None = None,
    subset: bool = False,
) -> dict[str, int]:
    """Pull jobs from adapters. subset=True uses title-based tier-1 only."""
    explicit_terms = search_terms is not None
    is_term_path = subset or explicit_terms

    stats = _empty_stats()
    pipeline = _make_pipeline()
    quota = default_quota_tracker()
    now = datetime.now(UTC)

    if is_term_path:
        terms = search_terms if explicit_terms else ()
        if not terms:
            logger.info("term ingest skipped: no terms in payload")
            return stats
        stats["terms_fetched"] = len(terms)
        await _run_term_ingest(session, terms, stats=stats, pipeline=pipeline, quota=quota, now=now)
        mark_terms_fetched(session, terms)
    else:
        await _run_nightly_sweep(session, stats=stats, pipeline=pipeline, quota=quota, now=now)

    stats["closed_non_us"] = close_non_us_open_jobs(session)
    stats["closed_expired_postings"] = close_expired_api_postings(session)

    session.flush()
    tier2_count = len(build_tier2_adapters(quota)) if not is_term_path else 0
    logger.info(
        "ingest persist complete stats=%s terms=%d tier2_boards=%d subset=%s",
        stats,
        stats["terms_fetched"],
        tier2_count,
        is_term_path,
    )
    return stats


def run_ingest(session: Session | None = None) -> dict[str, int]:
    own_session = session is None
    session = session or SessionLocal()
    try:
        stats = asyncio.run(pull_all_sources(session))
        if own_session:
            session.commit()
        return stats
    except Exception:
        if own_session:
            session.rollback()
        raise
    finally:
        if own_session:
            session.close()


def run_term_ingest(
    session: Session,
    terms: tuple[str, ...],
) -> dict[str, int]:
    """Fetch jobs for newly registered user target titles."""
    return asyncio.run(pull_all_sources(session, search_terms=terms, subset=True))
