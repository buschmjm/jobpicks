"""Access control tests (WS-2 role gate + public paths)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from api.access_control import (
    assert_jobs_role,
    is_public_path,
    require_jobs_role_enabled,
    verify_metrics_token,
)
from api.main import app
from fastapi import HTTPException
from fastapi.testclient import TestClient


def test_public_path_allowlist() -> None:
    assert is_public_path("/api/billing/webhook") is True
    assert is_public_path("/api/auth/config") is True
    assert is_public_path("/api/health") is True
    assert is_public_path("/metrics") is True
    assert is_public_path("/privacy") is True
    assert is_public_path("/welcome") is True
    assert is_public_path("/.well-known/apple-app-site-association") is True
    assert is_public_path("/api/profile/me") is False


def test_assert_jobs_role_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REQUIRE_JOBS_ROLE", raising=False)
    assert require_jobs_role_enabled() is False
    assert_jobs_role({"realm_access": {"roles": []}})


def test_assert_jobs_role_requires_jobs_role(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REQUIRE_JOBS_ROLE", "true")
    with pytest.raises(HTTPException) as exc:
        assert_jobs_role({"realm_access": {"roles": ["offline_access"]}})
    assert exc.value.status_code == 403


def test_assert_jobs_role_accepts_jobs_or_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REQUIRE_JOBS_ROLE", "true")
    assert_jobs_role({"realm_access": {"roles": ["jobs"]}})
    assert_jobs_role({"realm_access": {"roles": ["homelab-admin"]}})


def test_verify_metrics_token_accepts_internal_events_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERNAL_EVENTS_TOKEN", "metrics-secret")
    verify_metrics_token(x_metrics_token="metrics-secret")


def test_verify_metrics_token_rejects_bad_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERNAL_EVENTS_TOKEN", "metrics-secret")
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(HTTPException) as exc:
        verify_metrics_token(x_metrics_token="wrong")
    assert exc.value.status_code == 401


@pytest.fixture
def keycloak_role_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("AUTH_BACKEND", "keycloak")
    monkeypatch.setenv("KEYCLOAK_URL", "https://auth.example.com")
    monkeypatch.setenv("KEYCLOAK_REALM", "homelab")
    monkeypatch.setenv("KEYCLOAK_CLIENT_ID", "job-platform")
    monkeypatch.setenv("REQUIRE_JOBS_ROLE", "true")
    return TestClient(app)


def test_keycloak_user_without_jobs_role_gets_403(keycloak_role_client: TestClient) -> None:
    claims = {
        "email": "outsider@example.com",
        "realm_access": {"roles": ["offline_access"]},
    }
    with patch("api.deps.verify_access_token", return_value=claims):
        response = keycloak_role_client.get(
            "/api/billing/status",
            headers={"Authorization": "Bearer fake-token"},
        )
    assert response.status_code == 403


def test_well_known_routes_are_public() -> None:
    client = TestClient(app)
    apple = client.get("/.well-known/apple-app-site-association")
    android = client.get("/.well-known/assetlinks.json")
    assert apple.status_code == 200
    assert android.status_code == 200
    assert apple.headers.get("cache-control") == "public, max-age=300"
    assert android.headers.get("cache-control") == "public, max-age=300"


def test_welcome_marketing_page_is_public() -> None:
    client = TestClient(app)
    response = client.get("/welcome")
    assert response.status_code == 200
    assert "JobPicks" in response.text
    assert "text/html" in response.headers.get("content-type", "")
