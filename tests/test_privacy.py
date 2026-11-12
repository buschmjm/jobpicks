"""Privacy endpoint and retention pure-function tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from api.auth import create_session_token, stub_user_id_for_email
from api.main import app
from core.privacy import (
    EVENT_ANONYMIZE_AFTER_DAYS,
    RESUME_FILE_MAX_AGE_DAYS,
    anonymized_user_email,
    event_anonymize_cutoff,
    find_stale_resume_files,
    resume_storage_cutoff,
    scrub_event_payload,
    should_anonymize_event,
    should_purge_resume_file,
)
from fastapi.testclient import TestClient

client = TestClient(app)


def test_scrub_event_payload_removes_pii_keys() -> None:
    payload = {
        "email": "user@example.com",
        "event": "login",
        "nested": {"name": "Jane", "count": 3},
    }
    cleaned = scrub_event_payload(payload)
    assert "email" not in cleaned
    assert "name" not in cleaned.get("nested", {})
    assert cleaned["event"] == "login"
    assert cleaned["nested"]["count"] == 3


def test_scrub_event_payload_redacts_emails_in_strings() -> None:
    cleaned = scrub_event_payload({"note": "contact user@example.com please"})
    assert cleaned["note"] == "[redacted]"


def test_anonymized_user_email_format() -> None:
    user_id = uuid.uuid4()
    assert anonymized_user_email(user_id) == f"deleted-{user_id}@deleted.local"


def test_resume_storage_cutoff_default_age() -> None:
    now = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)
    cutoff = resume_storage_cutoff(now=now)
    assert cutoff == now - timedelta(days=RESUME_FILE_MAX_AGE_DAYS)


def test_should_purge_resume_file() -> None:
    now = datetime(2026, 8, 27, tzinfo=UTC)
    cutoff = resume_storage_cutoff(now=now)
    old = now - timedelta(days=RESUME_FILE_MAX_AGE_DAYS + 1)
    recent = now - timedelta(days=10)
    assert should_purge_resume_file(old, cutoff) is True
    assert should_purge_resume_file(recent, cutoff) is False


def test_find_stale_resume_files(tmp_path: Path) -> None:
    now = datetime(2026, 8, 27, tzinfo=UTC)
    cutoff = resume_storage_cutoff(now=now)
    stale_file = tmp_path / "resume-old.pdf"
    fresh_file = tmp_path / "resume-new.pdf"
    stale_file.write_bytes(b"old")
    fresh_file.write_bytes(b"new")

    stale_mtime = (now - timedelta(days=RESUME_FILE_MAX_AGE_DAYS + 5)).timestamp()
    fresh_mtime = (now - timedelta(days=1)).timestamp()
    import os

    os.utime(stale_file, (stale_mtime, stale_mtime))
    os.utime(fresh_file, (fresh_mtime, fresh_mtime))

    stale = find_stale_resume_files(tmp_path, cutoff)
    names = {item.path.name for item in stale}
    assert "resume-old.pdf" in names
    assert "resume-new.pdf" not in names


def test_should_anonymize_event() -> None:
    now = datetime(2026, 8, 27, tzinfo=UTC)
    cutoff = event_anonymize_cutoff(now=now)
    old = now - timedelta(days=EVENT_ANONYMIZE_AFTER_DAYS + 1)
    recent = now - timedelta(days=30)
    assert should_anonymize_event(old, cutoff) is True
    assert should_anonymize_event(recent, cutoff) is False


def test_privacy_policy_page() -> None:
    response = client.get("/privacy")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Privacy Policy" in response.text
    assert "CCPA" in response.text or "California" in response.text
    assert "delete" in response.text.lower()


def test_delete_my_data_requires_auth() -> None:
    response = client.delete("/api/privacy/delete-my-data")
    assert response.status_code == 401


def test_export_my_data_requires_auth() -> None:
    response = client.get("/api/privacy/export")
    assert response.status_code == 401


def test_export_my_data_success() -> None:
    email = "export-test@example.com"
    user_id = stub_user_id_for_email(email)
    session_token = create_session_token(user_id, email)

    mock_payload = {
        "exported_at": "2026-09-02T12:00:00+00:00",
        "user_id": str(user_id),
        "email": email,
        "profile": None,
        "todo_items": [],
    }
    mock_user = MagicMock()
    mock_user.id = user_id
    mock_user.email = email

    with (
        patch("api.deps.UserRepository") as mock_user_repo_cls,
        patch("api.deps.ProfileRepository") as mock_profile_repo_cls,
        patch("api.routers.privacy.export_user_data", return_value=mock_payload) as mock_export,
    ):
        mock_user_repo_cls.return_value.get_by_id.return_value = mock_user
        mock_profile_repo_cls.return_value.is_onboarding_complete.return_value = False
        response = client.get(
            "/api/privacy/export",
            cookies={"session": session_token},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == email
    assert body["user_id"] == str(user_id)
    assert body["data"]["todo_items"] == []
    mock_export.assert_called_once()
    assert mock_export.call_args[0][1] == user_id


def test_delete_my_data_success() -> None:
    email = "privacy-test@example.com"
    user_id = stub_user_id_for_email(email)
    session_token = create_session_token(user_id, email)

    mock_counts = {"profiles": 1, "events_anonymized": 2, "todo_items": 3}
    mock_user = MagicMock()
    mock_user.id = user_id
    mock_user.email = email

    with (
        patch("api.deps.UserRepository") as mock_user_repo_cls,
        patch("api.deps.ProfileRepository") as mock_profile_repo_cls,
        patch("api.routers.privacy.delete_user_data", return_value=mock_counts) as mock_delete,
    ):
        mock_user_repo_cls.return_value.get_by_id.return_value = mock_user
        mock_profile_repo_cls.return_value.is_onboarding_complete.return_value = False
        response = client.delete(
            "/api/privacy/delete-my-data",
            cookies={"session": session_token},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["deleted"] is True
    assert body["counts"] == mock_counts
    mock_delete.assert_called_once()
    assert mock_delete.call_args[0][1] == user_id


def test_delete_user_data_integration_mock_session() -> None:
    from api.services.privacy_service import delete_user_data

    user_id = uuid.uuid4()
    mock_user = MagicMock()
    mock_user.email = "test@example.com"
    mock_user.is_active = True

    mock_session = MagicMock()
    mock_session.get.return_value = mock_user
    mock_session.scalars.return_value.all.return_value = []

    def fake_execute(stmt):  # noqa: ANN001
        result = MagicMock()
        result.rowcount = 1
        return result

    mock_session.execute.side_effect = fake_execute

    with patch("api.services.privacy_service.delete_resume_files_for_user", return_value=0):
        counts = delete_user_data(mock_session, user_id)

    assert counts["profiles"] == 1
    assert mock_user.is_active is False
    assert mock_user.email == anonymized_user_email(user_id)
