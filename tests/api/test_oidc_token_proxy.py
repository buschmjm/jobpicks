"""Tests for Keycloak token proxy validation."""

from __future__ import annotations

import pytest
from api.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def keycloak_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("AUTH_BACKEND", "keycloak")
    monkeypatch.setenv("KEYCLOAK_URL", "https://auth.example.com")
    monkeypatch.setenv("KEYCLOAK_REALM", "homelab")
    monkeypatch.setenv("KEYCLOAK_CLIENT_ID", "job-platform")
    monkeypatch.setenv("APP_BASE_URL", "https://jobs.example.com")
    return TestClient(app)


def test_oidc_token_proxy_rejects_unknown_client(keycloak_client: TestClient) -> None:
    resp = keycloak_client.post(
        "/api/auth/oidc/token",
        data={
            "grant_type": "authorization_code",
            "client_id": "other-app",
            "code": "abc",
            "redirect_uri": "https://jobs.example.com/auth/callback",
            "code_verifier": "verifier",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid client_id"


def test_oidc_token_proxy_rejects_bad_redirect(keycloak_client: TestClient) -> None:
    resp = keycloak_client.post(
        "/api/auth/oidc/token",
        data={
            "grant_type": "authorization_code",
            "client_id": "job-platform",
            "code": "abc",
            "redirect_uri": "https://evil.example.com/auth/callback",
            "code_verifier": "verifier",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid redirect_uri"


from api.routers.auth import _allowed_redirect_uris


def test_allowed_redirect_uris_includes_alt_base(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_BASE_URL", "https://app.example.com/jobpicks")
    monkeypatch.setenv("APP_ALT_BASE_URLS", "https://jobs.example.com")
    monkeypatch.setenv("APP_MOUNT_PATH", "/jobpicks")
    uris = _allowed_redirect_uris()
    assert "https://app.example.com/jobpicks/auth/callback" in uris
    assert "https://jobs.example.com/jobpicks/auth/callback" in uris


def test_oidc_token_proxy_forwards_public_issuer(keycloak_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class _Response:
        content = b'{"access_token":"fresh"}'
        status_code = 200
        headers = {"content-type": "application/json"}

    class _Client:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *args: object) -> None:
            del args

        async def post(self, url: str, content: bytes, headers: dict[str, str]) -> _Response:
            captured["url"] = url
            captured["headers"] = headers
            captured["content"] = content
            return _Response()

    monkeypatch.setattr("api.routers.auth.httpx.AsyncClient", _Client)
    monkeypatch.setenv("KEYCLOAK_INTERNAL_URL", "http://keycloak.internal")

    resp = keycloak_client.post(
        "/api/auth/oidc/token",
        data={
            "grant_type": "refresh_token",
            "client_id": "job-platform",
            "refresh_token": "refresh-1",
        },
    )
    assert resp.status_code == 200
    assert captured["url"] == "http://keycloak.internal/realms/homelab/protocol/openid-connect/token"
    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert headers["X-Forwarded-Proto"] == "https"
    assert headers["X-Forwarded-Host"] == "auth.example.com"
    assert headers["X-Forwarded-Port"] == "443"


def test_oidc_token_proxy_rejects_password_grant(keycloak_client: TestClient) -> None:
    resp = keycloak_client.post(
        "/api/auth/oidc/token",
        data={
            "grant_type": "password",
            "client_id": "job-platform",
            "username": "user@example.com",
            "password": "secret",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Unsupported grant_type"


def test_auth_config_token_endpoint_matches_request_host(
    keycloak_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_BASE_URL", "https://app.example.com/jobpicks")
    monkeypatch.setenv("APP_ALT_BASE_URLS", "https://jobs.example.com")
    monkeypatch.setenv("APP_MOUNT_PATH", "/jobpicks")

    resp = keycloak_client.get(
        "/api/auth/config",
        headers={"host": "jobs.example.com"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "keycloak"
    assert body["token_endpoint"] == "https://jobs.example.com/jobpicks/api/auth/oidc/token"
