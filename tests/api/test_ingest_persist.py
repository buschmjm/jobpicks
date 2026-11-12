"""Tests for ingest runner helpers."""

from __future__ import annotations

from datetime import UTC, date, datetime

from ingest.runner import persist_job
from ingest.schema import StandardJob, WorkArrangement
from sqlalchemy.orm import Session


def _standard_job(**overrides: object) -> StandardJob:
    base = {
        "source": "jsearch",
        "source_url": "https://example.com/j/1",
        "title": "Registered Nurse",
        "company": "Acme Health",
        "location": "Austin, TX",
        "work_arrangement": WorkArrangement.ONSITE,
        "description": "Patient care",
        "date_posted": date(2026, 8, 1),
        "canonical_hash": "hash-nurse-1",
        "collected_timestamp": datetime.now(UTC),
    }
    base.update(overrides)
    return StandardJob(**base)  # type: ignore[arg-type]


def test_persist_job_creates_row(db_session: Session) -> None:
    job, created = persist_job(db_session, _standard_job())
    db_session.commit()
    assert created is True
    assert job.title == "Registered Nurse"
    assert job.apply_url == "https://example.com/j/1"
    assert job.ats_type is None
    assert job.ats_metadata.get("host") == "example.com"


def test_persist_job_stores_apply_url_fields(db_session: Session) -> None:
    gh_url = "https://boards.greenhouse.io/acme/jobs/42"
    job, created = persist_job(
        db_session,
        _standard_job(
            source="greenhouse",
            source_url=gh_url,
            apply_url=gh_url,
            ats_type="greenhouse",
            ats_metadata={"board_token": "acme", "posting_id": "42"},
            canonical_hash="hash-gh-42",
        ),
    )
    db_session.commit()
    assert created is True
    assert job.apply_url == gh_url
    assert job.ats_type == "greenhouse"
    assert job.ats_metadata["board_token"] == "acme"
