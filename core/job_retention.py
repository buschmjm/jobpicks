"""Job posting-age retention for API-sourced jobs."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import Date, cast, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement

from core.models import Job, JobStatus

API_JOB_MAX_AGE_DAYS = 30


def effective_posted_date(job: Job) -> date:
    """Posting date for retention; fall back to first_seen when date_posted is missing."""
    if job.date_posted is not None:
        return job.date_posted
    seen = job.first_seen
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=UTC)
    return seen.date()


def posted_cutoff_date(*, reference: date | None = None) -> date:
    today = reference or datetime.now(tz=UTC).date()
    return today - timedelta(days=API_JOB_MAX_AGE_DAYS)


def is_within_posting_window(job: Job, *, reference: date | None = None) -> bool:
    """True when an API-sourced job is still within the posting retention window."""
    if job.is_direct:
        return True
    return effective_posted_date(job) >= posted_cutoff_date(reference=reference)


def open_corpus_filter(*, reference: date | None = None) -> ColumnElement[bool]:
    """SQL filter: open API jobs within posting window; direct posts always eligible."""
    cutoff = posted_cutoff_date(reference=reference)
    effective = func.coalesce(Job.date_posted, cast(Job.first_seen, Date))
    return or_(Job.is_direct.is_(True), effective >= cutoff)


def close_expired_api_postings(session: Session, *, reference: date | None = None) -> int:
    """Close open API jobs older than the posting retention window."""
    cutoff = posted_cutoff_date(reference=reference)
    effective = func.coalesce(Job.date_posted, cast(Job.first_seen, Date))
    rows = session.scalars(
        select(Job).where(
            Job.status == JobStatus.OPEN.value,
            Job.is_direct.is_(False),
            effective < cutoff,
        )
    ).all()
    for job in rows:
        job.status = JobStatus.CLOSED
    if rows:
        session.flush()
    return len(rows)


def purge_closed_api_jobs(session: Session, *, reference: date | None = None) -> int:
    """Hard-delete closed API jobs past the posting retention window."""
    cutoff = posted_cutoff_date(reference=reference)
    effective = func.coalesce(Job.date_posted, cast(Job.first_seen, Date))
    rows = session.scalars(
        select(Job).where(
            Job.status == JobStatus.CLOSED.value,
            Job.is_direct.is_(False),
            effective < cutoff,
        )
    ).all()
    for job in rows:
        session.delete(job)
    if rows:
        session.flush()
    return len(rows)
