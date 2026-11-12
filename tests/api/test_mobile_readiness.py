"""Mobile readiness and region-gated billing API (WS-8)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from api.auth import create_session_token, stub_user_id_for_email
from api.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_mobile_readiness_public(client: TestClient) -> None:
    response = client.get("/api/mobile/readiness")
    assert response.status_code == 200
    data = response.json()
    assert "apple_universal_links_configured" in data
    assert "android_app_links_configured" in data
    assert "external_checkout_storefronts" in data
    assert data["external_checkout_storefronts"] == ["US"]


def test_billing_checkout_mobile_gb_forbidden(client: TestClient) -> None:
    email = "mobile-gb@example.com"
    user_id = stub_user_id_for_email(email)
    session_token = create_session_token(user_id, email)
    mock_user = MagicMock()
    mock_user.id = user_id
    mock_user.email = email

    with (
        patch("api.deps.UserRepository") as mock_user_repo_cls,
        patch("api.deps.ProfileRepository") as mock_profile_repo_cls,
    ):
        mock_user_repo_cls.return_value.get_by_id.return_value = mock_user
        mock_profile_repo_cls.return_value.is_onboarding_complete.return_value = False
        response = client.post(
            "/api/billing/checkout",
            cookies={"session": session_token},
            headers={"X-App-Client": "mobile", "X-App-Storefront": "GB"},
        )

    assert response.status_code == 403
    assert "supported app store regions" in response.json()["detail"].lower()
