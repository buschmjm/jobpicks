"""API tests for on-demand job description enrichment."""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

from api.main import app
from api.services.job_description_service import get_job_description
from core.models import Job, JobStatus, RemoteMode
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def test_get_job_description_enriches_truncated_snippet(db_session: Session) -> None:
    job = Job(
        company_name="Acme",
        title="Platform Engineer",
        normalized_title="platform engineer",
        description="A" * 499 + "…",
        canonical_hash=f"hash-{uuid4()}",
        primary_source="adzuna",
        remote_mode=RemoteMode.UNKNOWN,
        status=JobStatus.OPEN,
    )
    db_session.add(job)
    db_session.commit()

    full = ("Full posting body. " * 120).strip()
    with patch(
        "api.services.job_description_service.enrich_job_description",
        return_value=full,
    ):
        description, truncated, _, _ = get_job_description(db_session, job.id)

    assert description == full
    assert truncated is False
    assert db_session.get(Job, job.id).description == full


def test_job_description_requires_auth() -> None:
    client = TestClient(app)
    response = client.get(f"/api/jobs/{uuid4()}/description")
    assert response.status_code == 401
