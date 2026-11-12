"""FastAPI dependencies."""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Generator
from typing import Annotated

from core.database import get_session
from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from api.access_control import assert_jobs_role
from api.auth import verify_session_token
from api.keycloak_auth import auth_backend, verify_access_token
from api.repositories.profile_repo import ProfileRepository
from api.repositories.user_repo import UserRepository
from api.schemas import SessionUser

logger = logging.getLogger(__name__)


def get_db() -> Generator[Session, None, None]:
    """Database session dependency (delegates to core.database.get_session)."""
    yield from get_session()


DbSession = Annotated[Session, Depends(get_db)]


def _session_user_from_db(db: Session, user_id: uuid.UUID, email: str) -> SessionUser:
    user = UserRepository(db).get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    onboarding_complete = ProfileRepository(db).is_onboarding_complete(user_id)
    return SessionUser(
        id=user_id,
        email=email,
        onboarding_complete=onboarding_complete,
    )


async def get_current_user(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
    session: str | None = Cookie(default=None),
) -> SessionUser:
    if auth_backend() == "keycloak":
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
        token = authorization.split(" ", 1)[1].strip()
        try:
            claims = verify_access_token(token)
        except Exception as exc:
            logger.warning("Keycloak token rejected: %s: %s", type(exc).__name__, exc)
            try:
                import jwt as _jwt

                unverified = _jwt.decode(
                    token,
                    options={
                        "verify_signature": False,
                        "verify_aud": False,
                        "verify_exp": False,
                    },
                )
                logger.warning(
                    "unverified token iss=%s aud=%s azp=%s email=%s preferred_username=%s",
                    unverified.get("iss"),
                    unverified.get("aud"),
                    unverified.get("azp"),
                    unverified.get("email"),
                    unverified.get("preferred_username"),
                )
            except Exception:
                logger.warning("token was not a readable JWT")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid access token",
            ) from exc
        assert_jobs_role(claims)
        email = str(claims["email"]).lower()
        user = UserRepository(db).get_or_create_by_email(email)
        db.commit()
        return _session_user_from_db(db, user.id, email)

    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = verify_session_token(session)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    return _session_user_from_db(db, payload.user_id, payload.email)


async def get_optional_user(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
    session: str | None = Cookie(default=None),
) -> SessionUser | None:
    try:
        return await get_current_user(db, authorization, session)
    except HTTPException:
        return None


async def get_current_user_or_dev_header(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
    session: str | None = Cookie(default=None),
    x_test_user_email: Annotated[str | None, Header(alias="X-Test-User-Email")] = None,
) -> SessionUser:
    if os.environ.get("APP_ENV", "development") == "development" and x_test_user_email:
        user = UserRepository(db).get_or_create_by_email(x_test_user_email)
        db.commit()
        return _session_user_from_db(db, user.id, user.email)
    return await get_current_user(db, authorization, session)
