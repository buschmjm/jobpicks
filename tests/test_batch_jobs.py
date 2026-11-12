"""Tests for nightly batch job helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import uuid4

from core.batch_jobs import _needs_llm_normalize, embed_jobs_batch, normalize_jobs_batch
from core.models import Job, JobStatus
from inference.client import InferenceUnavailableError


def _job(source: str, *, skills: list[str] | None = None, raw: dict | None = None) -> Job:
    return Job(
        id=uuid4(),
        company_name="Acme",
        title="SRE",
        normalized_title="sre",
        canonical_hash="abc",
        primary_source=source,
        skills=skills,
        seniority_level="senior" if skills else None,
        first_seen=datetime.now(UTC),
        last_seen=datetime.now(UTC),
        status=JobStatus.OPEN,
        raw=raw or {},
    )


def test_needs_llm_normalize_skips_jsearch() -> None:
    job = _job("jsearch", skills=["go"])
    assert _needs_llm_normalize(job) is False


def test_needs_llm_normalize_adzuna_missing_skills() -> None:
    job = _job("adzuna", skills=None)
    assert _needs_llm_normalize(job) is True


def test_normalize_jobs_batch_applies_fields() -> None:
    session = MagicMock()
    job = _job("adzuna", skills=None)
    session.scalars.return_value.all.return_value = [job]

    with patch(
        "core.batch_jobs.extract_job_fields",
        return_value={
            "required_skills": ["python", "kubernetes"],
            "seniority_level": "senior",
            "work_arrangement": "remote",
            "salary_min": 140000,
            "salary_max": 170000,
            "salary_currency": "USD",
            "job_family": "platform",
            "preferred_skills": [],
            "employment_type": "full_time",
            "years_experience_min": 5,
            "years_experience_max": 8,
            "industry": "tech",
        },
    ):
        stats = normalize_jobs_batch(session, batch_size=10)

    assert stats["normalized"] == 1
    assert job.skills == ["python", "kubernetes"]
    assert job.raw.get("llm_normalized") is True


def test_embed_jobs_batch_skips_when_unavailable() -> None:
    session = MagicMock()
    job = _job("jsearch", skills=["go"])
    job.embedding = None
    session.scalars.return_value.all.return_value = [job]

    mock_client = MagicMock()
    mock_client.embed_many.side_effect = InferenceUnavailableError("down")

    with patch("core.batch_jobs.EmbeddingClient", return_value=mock_client):
        stats = embed_jobs_batch(session, batch_size=10)

    assert stats["embedded"] == 0
    assert stats["errors"] == 1
