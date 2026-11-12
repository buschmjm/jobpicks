"""Force legacy auth in unit tests (Keycloak is integration-tested on homelab)."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _legacy_auth_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_BACKEND", "legacy")
    monkeypatch.setenv("INTERNAL_EVENTS_TOKEN", "dev-internal-events-token")
    monkeypatch.delenv("KEYCLOAK_URL", raising=False)
