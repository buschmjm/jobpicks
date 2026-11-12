"""Access control helpers (Keycloak roles, public routes)."""

from __future__ import annotations

import os
from typing import Any

from fastapi import Header, HTTPException, Request, status

# Routes that must never require the Keycloak `jobs` role (research brief A7).
PUBLIC_API_PREFIXES: tuple[str, ...] = (
    "/api/billing/webhook",
    "/api/auth/oidc/token",
    "/api/auth/config",
    "/api/email/unsubscribe/",
    "/api/mobile/",
    "/api/health",
    "/health",
    "/metrics",
    "/privacy",
    "/terms",
    "/.well-known/",
)


def require_jobs_role_enabled() -> bool:
    return os.environ.get("REQUIRE_JOBS_ROLE", "false").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def realm_roles_from_claims(claims: dict[str, Any]) -> set[str]:
    realm_access = claims.get("realm_access")
    if not isinstance(realm_access, dict):
        return set()
    roles = realm_access.get("roles")
    if not isinstance(roles, list):
        return set()
    return {str(role) for role in roles}


def assert_jobs_role(claims: dict[str, Any]) -> None:
    if not require_jobs_role_enabled():
        return
    roles = realm_roles_from_claims(claims)
    if "jobs" in roles or "homelab-admin" in roles:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Access restricted. Ask an admin for a JobPicks invite.",
    )


def is_public_path(path: str) -> bool:
    if path in {"/health", "/metrics", "/privacy", "/terms", "/welcome"}:
        return True
    return any(path.startswith(prefix) for prefix in PUBLIC_API_PREFIXES)


def verify_metrics_token(
    x_metrics_token: str | None = Header(default=None, alias="X-Metrics-Token"),
) -> None:
    expected = (
        os.environ.get("METRICS_TOKEN", "").strip()
        or os.environ.get("INTERNAL_EVENTS_TOKEN", "").strip()
    )
    if not expected:
        if os.environ.get("APP_ENV", "development") == "development":
            return
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Metrics token not configured",
        )
    if x_metrics_token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid metrics token",
        )


def verify_public_path_access(request: Request) -> None:
    """Middleware helper: no-op placeholder for explicit public route documentation."""
    _ = request
