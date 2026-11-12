"""Session and magic-link token utilities."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import EmailStr

# Magic link tokens: single-use, 15-minute expiry (plan §12)
MAGIC_LINK_MAX_AGE_SECONDS = 15 * 60
SESSION_MAX_AGE_SECONDS = 30 * 24 * 60 * 60  # 30 days


def _secret_key() -> str:
    key = os.environ.get("SECRET_KEY")
    if not key:
        if os.environ.get("APP_ENV", "development") == "production":
            raise RuntimeError("SECRET_KEY must be set in production")
        key = "dev-insecure-change-me"
    return key


def _serializer(salt: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(_secret_key(), salt=salt)


@dataclass
class MagicLinkPayload:
    email: str
    token_id: str


@dataclass
class SessionPayload:
    user_id: UUID
    email: str
    issued_at: datetime


# In-memory stores for stub phase — replace with Redis/Postgres in E2.2+
_used_magic_tokens: set[str] = set()
_sessions: dict[str, SessionPayload] = {}


def create_magic_link_token(email: EmailStr) -> str:
    token_id = secrets.token_urlsafe(16)
    payload = {"email": str(email).lower(), "tid": token_id}
    return _serializer("magic-link").dumps(payload)


def verify_magic_link_token(token: str) -> MagicLinkPayload:
    """Verify token signature, expiry, and single-use constraint."""
    try:
        data: dict[str, Any] = _serializer("magic-link").loads(
            token, max_age=MAGIC_LINK_MAX_AGE_SECONDS
        )
    except SignatureExpired as exc:
        raise ValueError("Magic link expired") from exc
    except BadSignature as exc:
        raise ValueError("Invalid magic link") from exc

    token_id = data.get("tid")
    email = data.get("email")
    if not token_id or not email:
        raise ValueError("Invalid magic link payload")

    if token_id in _used_magic_tokens:
        raise ValueError("Magic link already used")

    _used_magic_tokens.add(token_id)
    return MagicLinkPayload(email=email, token_id=token_id)


def create_session_token(user_id: UUID, email: str) -> str:
    session_id = secrets.token_urlsafe(32)
    _sessions[session_id] = SessionPayload(
        user_id=user_id, email=email, issued_at=datetime.now(UTC)
    )
    return session_id


def verify_session_token(session_id: str) -> SessionPayload | None:
    session = _sessions.get(session_id)
    if not session:
        return None
    age = (datetime.now(UTC) - session.issued_at).total_seconds()
    if age > SESSION_MAX_AGE_SECONDS:
        _sessions.pop(session_id, None)
        return None
    return session


def revoke_session(session_id: str) -> None:
    _sessions.pop(session_id, None)


def session_cookie_settings() -> dict[str, Any]:
    """HttpOnly, Secure, SameSite=Lax per plan §13."""
    secure = os.environ.get("APP_ENV", "development") != "development"
    return {
        "key": "session",
        "httponly": True,
        "secure": secure,
        "samesite": "lax",
        "max_age": SESSION_MAX_AGE_SECONDS,
        "path": "/",
    }


def stub_user_id_for_email(email: str) -> UUID:
    """Deterministic stub user id until DB wired."""
    import hashlib

    digest = hashlib.sha256(email.encode()).digest()
    return UUID(bytes=digest[:16], version=4)


def new_uuid() -> UUID:
    return uuid4()
