"""Resolve full job descriptions for truncated aggregator snippets."""

import logging
import os
from collections.abc import Callable
from functools import lru_cache
from typing import Any
from urllib.parse import urlencode

import httpx
from ingest.adapters.greenhouse import _map_greenhouse_record
from ingest.adapters.lever import _map_lever_record
from ingest.companies_loader import CompanySeed, load_company_seeds
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.apply.ats_detect import detect_ats
from core.apply.job_from_url import JobFromUrlError, _fetch_greenhouse_job, _fetch_lever_job
from core.job_description import (
    description_looks_truncated,
    descriptions_match_job,
    prefer_description,
    token_similarity,
)
from core.models import Job, JobStatus

logger = logging.getLogger(__name__)

_PREFERRED_SOURCES = ("greenhouse", "lever", "jsearch", "usajobs", "remotive")
_JSEARCH_BASE = os.environ.get("JSEARCH_BASE_URL", "https://api.openwebninja.com/jsearch/search-v2")
_GREENHOUSE_LIST_API = "https://boards-api.greenhouse.io/v1/boards"
_LEVER_LIST_API = "https://api.lever.co/v0/postings"


@lru_cache(maxsize=1)
def _company_seeds() -> tuple[CompanySeed, ...]:
    return tuple(load_company_seeds())


def _match_company_seed(company_name: str) -> CompanySeed | None:
    best: CompanySeed | None = None
    best_score = 0.0
    for seed in _company_seeds():
        score = token_similarity(company_name, seed.name)
        if score > best_score:
            best = seed
            best_score = score
    if best is not None and best_score >= 0.5:
        return best
    return None


def _enrich_from_company_seed(job: Job) -> str | None:
    seed = _match_company_seed(job.company_name)
    if seed is None:
        return None

    if seed.greenhouse:
        url = f"{_GREENHOUSE_LIST_API}/{seed.greenhouse}/jobs?content=true"
        try:
            response = httpx.get(url, timeout=20.0)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.info("greenhouse board lookup failed board=%s: %s", seed.greenhouse, exc)
            return None
        payload = response.json()
        for record in payload.get("jobs") or []:
            if not isinstance(record, dict):
                continue
            title = str(record.get("title") or "")
            if not descriptions_match_job(
                job_title=job.title,
                company_name=job.company_name,
                candidate_title=title,
                candidate_company=seed.name,
            ):
                continue
            posting_id = record.get("id")
            if posting_id is None:
                continue
            try:
                full_record = _fetch_greenhouse_job(
                    board_token=seed.greenhouse,
                    posting_id=str(posting_id),
                )
            except JobFromUrlError:
                continue
            mapped = _map_greenhouse_record(
                full_record,
                company_name=seed.name,
                collected_at=job.last_seen,
            )
            if mapped.description and not description_looks_truncated(mapped.description):
                return mapped.description

    if seed.lever:
        try:
            response = httpx.get(
                f"{_LEVER_LIST_API}/{seed.lever}",
                params={"mode": "json"},
                timeout=20.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.info("lever board lookup failed site=%s: %s", seed.lever, exc)
            return None
        payload = response.json()
        postings = payload if isinstance(payload, list) else []
        for record in postings:
            if not isinstance(record, dict):
                continue
            title = str(record.get("text") or record.get("title") or "")
            if not descriptions_match_job(
                job_title=job.title,
                company_name=job.company_name,
                candidate_title=title,
                candidate_company=seed.name,
            ):
                continue
            posting_id = str(record.get("id") or "")
            if not posting_id:
                continue
            try:
                full_record = _fetch_lever_job(posting_id=posting_id)
            except JobFromUrlError:
                continue
            mapped = _map_lever_record(
                full_record,
                company_name=seed.name,
                collected_at=job.last_seen,
            )
            if mapped.description and not description_looks_truncated(mapped.description):
                return mapped.description
    return None


def find_duplicate_description(session: Session, job: Job) -> str | None:
    """Reuse a fuller description from another open job with the same role."""
    if not description_looks_truncated(job.description):
        return None

    stmt = (
        select(Job.description, Job.title, Job.company_name)
        .where(Job.id != job.id)
        .where(Job.status == JobStatus.OPEN)
        .where(Job.normalized_title == job.normalized_title)
        .where(func.length(Job.description) > 600)
        .where(Job.primary_source.in_(_PREFERRED_SOURCES))
        .order_by(func.length(Job.description).desc())
        .limit(12)
    )
    rows = session.execute(stmt).all()
    for description, title, company in rows:
        if not description:
            continue
        if descriptions_match_job(
            job_title=job.title,
            company_name=job.company_name,
            candidate_title=str(title),
            candidate_company=str(company),
        ):
            return str(description)
    return None


def _enrich_from_ats(job: Job) -> str | None:
    for url in (job.apply_url, job.source_url):
        cleaned = (url or "").strip()
        if not cleaned:
            continue
        ats_type, metadata = detect_ats(cleaned)
        if ats_type == "greenhouse":
            board_token = str(metadata.get("board_token") or "").strip()
            posting_id = str(metadata.get("posting_id") or "").strip()
            if not board_token or not posting_id:
                continue
            try:
                record = _fetch_greenhouse_job(board_token=board_token, posting_id=posting_id)
            except JobFromUrlError:
                continue
            mapped = _map_greenhouse_record(
                record,
                company_name=job.company_name,
                collected_at=job.last_seen,
            )
            return mapped.description
        if ats_type == "lever":
            posting_id = str(metadata.get("posting_id") or "").strip()
            if not posting_id:
                continue
            try:
                record = _fetch_lever_job(posting_id=posting_id)
            except JobFromUrlError:
                continue
            mapped = _map_lever_record(
                record,
                company_name=job.company_name,
                collected_at=job.last_seen,
            )
            return mapped.description
    return None


def _jsearch_headers() -> dict[str, str]:
    api_key = os.environ.get("JSEARCH_API_KEY", "").strip()
    if not api_key:
        return {}
    if os.environ.get("JSEARCH_USE_RAPIDAPI", "").lower() in {"1", "true", "yes"}:
        return {
            "X-RapidAPI-Key": api_key,
            "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
        }
    return {"X-API-Key": api_key}


def _jsearch_search_url(*, title: str, company: str) -> str:
    query = " ".join(part for part in (title.strip(), company.strip()) if part)
    params = {
        "query": query,
        "page": 1,
        "num_pages": 1,
        "country": "us",
    }
    return f"{_JSEARCH_BASE}?{urlencode(params)}"


def _extract_jsearch_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data") or payload.get("jobs") or []
    if isinstance(data, dict):
        data = data.get("jobs") or data.get("results") or []
    return [item for item in data if isinstance(item, dict)]


def _enrich_from_jsearch(job: Job) -> str | None:
    headers = _jsearch_headers()
    if not headers:
        return None

    url = _jsearch_search_url(title=job.title, company=job.company_name)
    try:
        response = httpx.get(url, headers=headers, timeout=20.0)
    except httpx.HTTPError as exc:
        logger.warning("jsearch description lookup failed: %s", exc)
        return None

    if response.status_code == 429:
        logger.info("jsearch description lookup rate limited for job=%s", job.id)
        return None
    if response.status_code >= 400:
        logger.warning(
            "jsearch description lookup status=%s job=%s",
            response.status_code,
            job.id,
        )
        return None

    payload = response.json()
    if not isinstance(payload, dict):
        return None

    best: str | None = None
    best_len = 0
    for record in _extract_jsearch_results(payload):
        candidate_title = str(record.get("job_title") or "")
        candidate_company = str(record.get("employer_name") or "")
        if not descriptions_match_job(
            job_title=job.title,
            company_name=job.company_name,
            candidate_title=candidate_title,
            candidate_company=candidate_company,
        ):
            continue
        description = str(record.get("job_description") or "").strip()
        if not description or description_looks_truncated(description):
            continue
        if len(description) > best_len:
            best = description
            best_len = len(description)
    return best


def enrich_job_description(session: Session, job: Job) -> str | None:
    """Return a fuller description for a truncated job, if one can be resolved."""
    current = (job.description or "").strip()
    if not description_looks_truncated(current):
        return current or None

    resolvers: tuple[Callable[[], str | None], ...] = (
        lambda: find_duplicate_description(session, job),
        lambda: _enrich_from_ats(job),
        lambda: _enrich_from_company_seed(job),
        lambda: _enrich_from_jsearch(job),
    )
    for resolver in resolvers:
        try:
            candidate = resolver()
        except Exception as exc:
            logger.warning("description enrich resolver failed job=%s: %s", job.id, exc)
            candidate = None
        chosen = prefer_description(current, candidate)
        if chosen and not description_looks_truncated(chosen):
            return chosen
    return current or None
