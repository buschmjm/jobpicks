"""Keycloak OIDC access-token validation (homelab SSO)."""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt

logger = logging.getLogger(__name__)

_JWKS_TTL_SECONDS = 3600
_jwks_cache: dict[str, tuple[float, dict[str, Any]]] = {}


@dataclass(frozen=True)
class KeycloakSettings:
    url: str
    internal_url: str
    realm: str
    client_id: str

    @property
    def issuer(self) -> str:
        return f"{self.url.rstrip('/')}/realms/{self.realm}"

    @property
    def internal_issuer(self) -> str:
        return f"{self.internal_url.rstrip('/')}/realms/{self.realm}"

    @property
    def jwks_uri(self) -> str:
        return f"{self.internal_issuer}/protocol/openid-connect/certs"

    @property
    def token_uri(self) -> str:
        return f"{self.internal_issuer}/protocol/openid-connect/token"

    @property
    def userinfo_uri(self) -> str:
        return f"{self.internal_issuer}/protocol/openid-connect/userinfo"


def get_keycloak_settings() -> KeycloakSettings | None:
    url = os.environ.get("KEYCLOAK_URL", "").strip()
    if not url:
        return None
    internal = os.environ.get("KEYCLOAK_INTERNAL_URL", "").strip() or url
    return KeycloakSettings(
        url=url,
        internal_url=internal,
        realm=os.environ.get("KEYCLOAK_REALM", "homelab").strip() or "homelab",
        client_id=os.environ.get("KEYCLOAK_CLIENT_ID", "job-platform").strip() or "job-platform",
    )


def auth_backend() -> str:
    explicit = os.environ.get("AUTH_BACKEND", "").strip().lower()
    if explicit:
        return explicit
    return "keycloak" if get_keycloak_settings() is not None else "legacy"


def _fetch_jwks(jwks_uri: str) -> dict[str, Any]:
    cached = _jwks_cache.get(jwks_uri)
    now = time.monotonic()
    if cached and now - cached[0] < _JWKS_TTL_SECONDS:
        return cached[1]
    with httpx.Client(timeout=10.0) as client:
        resp = client.get(jwks_uri)
        resp.raise_for_status()
        body = resp.json()
    if not isinstance(body, dict) or "keys" not in body:
        raise jwt.InvalidTokenError("JWKS response was invalid")
    _jwks_cache[jwks_uri] = (now, body)
    return body


def _signing_key(token: str, jwks: dict[str, Any]) -> Any:
    header = jwt.get_unverified_header(token)
    kid = header.get("kid")
    for jwk in jwks.get("keys", []):
        if kid and jwk.get("kid") != kid:
            continue
        return jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))
    raise jwt.InvalidTokenError("No matching signing key")


def _audiences(claims: dict[str, Any]) -> list[str]:
    aud = claims.get("aud")
    if isinstance(aud, list):
        return [str(item) for item in aud if item]
    if aud:
        return [str(aud)]
    return []


def token_is_for_client(claims: dict[str, Any], client_id: str) -> bool:
    """Keycloak access tokens often use aud=account and may omit azp."""
    azp = claims.get("azp")
    audiences = _audiences(claims)
    if azp == client_id or client_id in audiences:
        return True
    return bool(azp in (None, "") and ("account" in audiences or not audiences))


def principal_email(claims: dict[str, Any]) -> str | None:
    email = claims.get("email")
    if email:
        return str(email).lower().strip()
    username = str(claims.get("preferred_username") or "").strip()
    if "@" in username:
        return username.lower()
    if username:
        return f"{username.lower()}@homelab.local"
    sub = claims.get("sub")
    if sub:
        return f"{str(sub).lower()}@homelab.local"
    return None


def _email_from_userinfo(token: str, settings: KeycloakSettings) -> str:
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(settings.userinfo_uri, headers={"Authorization": f"Bearer {token}"})
            resp.raise_for_status()
            info = resp.json()
    except httpx.HTTPError as exc:
        raise jwt.InvalidTokenError("Unable to load user profile") from exc

    email = principal_email(info if isinstance(info, dict) else {})
    if not email:
        raise jwt.InvalidTokenError("Token missing email claim")
    return email


def verify_access_token(token: str) -> dict[str, Any]:
    settings = get_keycloak_settings()
    if settings is None:
        raise RuntimeError("KEYCLOAK_URL is not configured")

    try:
        jwks = _fetch_jwks(settings.jwks_uri)
    except httpx.HTTPError as exc:
        logger.warning("JWKS fetch failed from %s: %s", settings.jwks_uri, exc)
        raise jwt.InvalidTokenError("Unable to load signing keys") from exc

    try:
        key = _signing_key(token, jwks)
    except jwt.InvalidTokenError:
        _jwks_cache.pop(settings.jwks_uri, None)
        jwks = _fetch_jwks(settings.jwks_uri)
        key = _signing_key(token, jwks)

    claims: dict[str, Any] = jwt.decode(
        token,
        key,
        algorithms=["RS256"],
        issuer=settings.issuer,
        leeway=120,
        options={"verify_aud": False},
    )

    if not token_is_for_client(claims, settings.client_id):
        raise jwt.InvalidTokenError("Token was not issued for this application")

    email = principal_email(claims)
    if not email:
        email = _email_from_userinfo(token, settings)
    claims["email"] = email

    return claims
