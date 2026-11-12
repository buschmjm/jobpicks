"""Workstream D/E API tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from api.main import app
from core.instrumentation import track_client_event
from core.metrics import DashboardMetrics
from core.models import User
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def test_track_event_requires_auth() -> None:
    client = TestClient(app)
    response = client.post("/api/events/track", json={"type": "deck_opened"})
    assert response.status_code == 401


def test_track_client_event_persists(db_session: Session) -> None:
    user = User(email="deck@example.com", is_active=True)
    db_session.add(user)
    db_session.flush()
    track_client_event(db_session, user_id=user.id, event_type="deck_opened")
    db_session.commit()


def test_metrics_endpoint() -> None:
    with patch(
        "api.routers.metrics.render_prometheus_metrics",
        return_value='jobdeck_users_total{tier="free"} 1\n',
    ):
        client = TestClient(app)
        response = client.get(
            "/metrics",
            headers={"X-Metrics-Token": "dev-internal-events-token"},
        )
    assert response.status_code == 200
    assert "jobdeck_users_total" in response.text


def test_metrics_endpoint_rejects_missing_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    client = TestClient(app)
    response = client.get("/metrics")
    assert response.status_code == 401


def test_admin_summary_json() -> None:
    stub = DashboardMetrics(
        dau=1,
        wau=2,
        swipes_per_session=3.0,
        right_swipe_rate=0.25,
        queue_depth=4,
        pro_users=1,
        free_users=3,
        referrals_total=2,
        digests_sent_24h=5,
        digest_open_rate_24h=0.4,
        llm_calls_24h=6,
    )
    with patch("api.routers.admin.compute_dashboard", return_value=stub):
        client = TestClient(app)
        response = client.get("/admin/api/summary", headers={"x-admin-secret": "dev-admin-secret"})
    assert response.status_code == 200
    body = response.json()
    assert body["pro_users"] == 1
    assert body["llm_calls_24h"] == 6
