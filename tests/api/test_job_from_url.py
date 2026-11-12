"""Tests for user-supplied job URL import."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from api.main import app
from api.schemas import JobFromUrlRequest
from api.services.job_import_service import job_import_service
from core.apply.job_from_url import JobFromUrlError, standard_job_from_url
from fastapi.testclient import TestClient
from ingest.schema import StandardJob

from tests.api.test_application_packet import _seed_todo


def test_standard_job_from_url_requires_http() -> None:
    with pytest.raises(JobFromUrlError, match="http"):
        standard_job_from_url("not-a-url")


def test_standard_job_from_url_greenhouse_parses(monkeypatch: pytest.MonkeyPatch) -> None:

    gh_record = {
        "id": 123,
        "title": "TPM",
        "absolute_url": "https://boards.greenhouse.io/acme/jobs/123",
        "location": {"name": "Remote"},
        "content": "Lead programs",
        "updated_at": "2026-08-01T00:00:00Z",
    }

    def fake_fetch(**_kwargs):
        return gh_record

    monkeypatch.setattr("core.apply.job_from_url._fetch_greenhouse_job", fake_fetch)
    job = standard_job_from_url("https://boards.greenhouse.io/acme/jobs/123")
    assert job.title == "TPM"
    assert job.ats_type == "greenhouse"
    assert job.apply_url == "https://boards.greenhouse.io/acme/jobs/123"
    assert job.canonical_hash


def test_import_from_url_creates_todo(db_session) -> None:
    user_id, _, _ = _seed_todo(db_session)
    std = StandardJob(
        title="Imported",
        company="Acme",
        location="Remote",
        description="desc",
        source="user_url",
        source_url="https://boards.greenhouse.io/acme/jobs/99",
        collected_timestamp=__import__("datetime").datetime.now(__import__("datetime").UTC),
        canonical_hash="import-hash-1",
        date_posted=__import__("datetime").date.today(),
    )
    with patch("api.services.job_import_service.standard_job_from_url", return_value=std):
        result = job_import_service.import_from_url(
            db_session,
            user_id,
            JobFromUrlRequest(url="https://boards.greenhouse.io/acme/jobs/99", generate_packet=False),
        )
    assert result.title == "Imported"
    assert result.todo_item_id is not None
    assert result.packet_status == "skipped"


def test_jobs_from_url_requires_auth() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/jobs/from-url",
        json={"url": "https://boards.greenhouse.io/acme/jobs/88"},
    )
    assert response.status_code == 401
