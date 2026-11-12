"""Admin dashboard route tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from api.main import app
from api.routers import admin as admin_router
from core.metrics import DashboardMetrics, QuotaSnapshot, SourceHealthRow
from fastapi.testclient import TestClient

client = TestClient(app)


@pytest.fixture(autouse=True)
def _admin_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("ADMIN_SECRET", "test-admin-secret")


def test_admin_requires_secret() -> None:
    response = client.get("/admin")
    assert response.status_code == 401


def test_admin_dashboard_renders_with_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_metrics = DashboardMetrics(
        dau=3,
        wau=10,
        swipes_per_session=4.2,
        right_swipe_rate=0.33,
        queue_depth=99,
        source_health=[SourceHealthRow("jsearch", 5, datetime.now(UTC), "healthy")],
        quota=[QuotaSnapshot("jsearch", 12, 100, datetime.now(UTC).date())],
        event_counts={"swipe_right": 7},
    )
    monkeypatch.setattr(admin_router, "compute_dashboard", lambda _session: stub_metrics)
    response = client.get("/admin", headers={"X-Admin-Secret": "test-admin-secret"})
    assert response.status_code == 200
    assert "Admin dashboard" in response.text
    assert "99" in response.text


def test_events_log_endpoint_accepts_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    from uuid import uuid4

    from api.routers import events as events_router

    class _FakeEvent:
        event_id = uuid4()

    monkeypatch.setattr(
        events_router,
        "log_event",
        lambda _session, **kwargs: _FakeEvent(),
    )
    response = client.post(
        "/api/events/log",
        json={"type": "login", "payload": {"source": "test"}},
        headers={"X-Internal-Token": "dev-internal-events-token"},
    )
    assert response.status_code == 201
    assert "event_id" in response.json()


def test_events_log_requires_internal_token() -> None:
    response = client.post(
        "/api/events/log",
        json={"type": "login", "payload": {"source": "test"}},
    )
    assert response.status_code == 401
