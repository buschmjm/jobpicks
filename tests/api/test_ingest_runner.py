"""Persist/upsert tests for ingest runner (needs DB fixture)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from ingest.runner import persist_job
from ingest.schema import StandardJob, WorkArrangement
from sqlalchemy.orm import Session


def _standard_job(**overrides: object) -> StandardJob:
    base = {
        "source": "greenhouse",
        "source_url": "https://example.com/j/1",
        "title": "Software Engineer",
        "company": "Acme",
        "location": "Remote",
        "work_arrangement": WorkArrangement.REMOTE,
        "description": "Build web apps",
        "date_posted": date(2026, 8, 1),
        "canonical_hash": "hash-upsert",
        "collected_timestamp": datetime.now(UTC),
    }
    base.update(overrides)
    return StandardJob(**base)  # type: ignore[arg-type]


def test_persist_job_upsert(db_session: Session) -> None:
    job = _standard_job()
    row, created = persist_job(db_session, job)
    assert created is True
    assert row.title == "Software Engineer"

    updated = _standard_job(title="Platform Engineer")
    row2, created2 = persist_job(db_session, updated)
    assert created2 is False
    assert row2.id == row.id
    assert row2.title == "Platform Engineer"
