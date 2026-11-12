"""Tests for API job posting retention."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from core.job_retention import (
    API_JOB_MAX_AGE_DAYS,
    close_expired_api_postings,
    effective_posted_date,
    is_within_posting_window,
    posted_cutoff_date,
)
from core.models import Job, JobStatus


def _job(*, posted: date | None, first_seen: datetime, is_direct: bool = False) -> Job:
    return Job(
        company_name="Acme",
        title="Engineer",
        normalized_title="engineer",
        canonical_hash="hash",
        status=JobStatus.OPEN,
        date_posted=posted,
        first_seen=first_seen,
        last_seen=first_seen,
        is_direct=is_direct,
        raw={},
    )


def test_effective_posted_date_prefers_date_posted() -> None:
    job = _job(posted=date(2026, 7, 1), first_seen=datetime(2026, 8, 1, tzinfo=UTC))
    assert effective_posted_date(job) == date(2026, 7, 1)


def test_effective_posted_date_falls_back_to_first_seen() -> None:
    seen = datetime(2026, 7, 15, tzinfo=UTC)
    job = _job(posted=None, first_seen=seen)
    assert effective_posted_date(job) == date(2026, 7, 15)


def test_api_job_outside_window() -> None:
    old = date.today() - timedelta(days=API_JOB_MAX_AGE_DAYS + 1)
    job = _job(posted=old, first_seen=datetime.now(tz=UTC))
    assert not is_within_posting_window(job)


def test_direct_job_exempt_from_window() -> None:
    old = date.today() - timedelta(days=API_JOB_MAX_AGE_DAYS + 10)
    job = _job(posted=old, first_seen=datetime.now(tz=UTC), is_direct=True)
    assert is_within_posting_window(job)


def test_posted_cutoff_is_30_days() -> None:
    assert posted_cutoff_date(reference=date(2026, 8, 28)) == date(2026, 7, 29)


def test_close_expired_api_postings_closes_old_open_jobs() -> None:

    # Pure unit logic without DB: verify function sets status on in-memory rows
    old = date.today() - timedelta(days=API_JOB_MAX_AGE_DAYS + 5)
    job = _job(posted=old, first_seen=datetime.now(tz=UTC))
    assert job.status == JobStatus.OPEN

    class _FakeSession:
        def scalars(self, _stmt):  # noqa: ANN001
            class _Result:
                def all(self_inner):  # noqa: ANN001
                    return [job]

            return _Result()

        def flush(self) -> None:
            return None

    closed = close_expired_api_postings(_FakeSession())  # type: ignore[arg-type]
    assert closed == 1
    assert job.status == JobStatus.CLOSED
