"""Email unsubscribe and resubscribe (Workstream C1)."""

from __future__ import annotations

from typing import Literal, cast

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse

from api.deps import DbSession, get_current_user
from api.email import email_backend_status
from api.schemas import EmailPreferencesResponse, EmailStatusResponse, SessionUser
from api.services.revenue_service import email_preferences_service

router = APIRouter(prefix="/email", tags=["email"])


@router.get("/unsubscribe/{token}", response_class=HTMLResponse)
def unsubscribe_email(token: str, db: DbSession) -> HTMLResponse:
    try:
        user = email_preferences_service.unsubscribe_by_token(db, token)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    db.commit()
    return HTMLResponse(
        content=(
            "<!DOCTYPE html><html><body style='font-family:system-ui;max-width:480px;margin:40px auto;'>"
            f"<h1>Unsubscribed</h1><p>{user.email} will no longer receive JobDeck digest emails.</p>"
            "<p>You can re-enable digests anytime from Settings while signed in.</p>"
            "</body></html>"
        ),
        status_code=status.HTTP_200_OK,
    )


@router.post("/unsubscribe", response_model=EmailPreferencesResponse)
def unsubscribe_authenticated(
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> EmailPreferencesResponse:
    try:
        email_preferences_service.unsubscribe(db, user.id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    db.commit()
    from core.models import User

    db_user = db.get(User, user.id)
    if db_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return EmailPreferencesResponse(
        digest_enabled=False,
        unsubscribe_url=email_preferences_service.unsubscribe_url(db_user),
    )


@router.get("/status", response_model=EmailStatusResponse)
def email_status(
    user: SessionUser = Depends(get_current_user),
) -> EmailStatusResponse:
    """SMTP readiness for Settings and deploy smoke tests."""
    _ = user
    status_payload = email_backend_status()
    backend = cast(Literal["smtp", "log"], status_payload["backend"])
    return EmailStatusResponse(
        backend=backend,
        configured=bool(status_payload["configured"]),
        ready=bool(status_payload["ready"]),
        from_domain=status_payload.get("from_domain"),  # type: ignore[arg-type]
    )


@router.post("/resubscribe", response_model=EmailPreferencesResponse)
def resubscribe_email(
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> EmailPreferencesResponse:
    try:
        email_preferences_service.resubscribe(db, user.id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    db.commit()
    from core.models import User

    db_user = db.get(User, user.id)
    if db_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return EmailPreferencesResponse(
        digest_enabled=db_user.unsubscribed_at is None,
        unsubscribe_url=email_preferences_service.unsubscribe_url(db_user),
    )


@router.get("/preferences", response_model=EmailPreferencesResponse)
def email_preferences(
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> EmailPreferencesResponse:
    from core.models import User

    db_user = db.get(User, user.id)
    if db_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return EmailPreferencesResponse(
        digest_enabled=db_user.unsubscribed_at is None,
        unsubscribe_url=email_preferences_service.unsubscribe_url(db_user),
    )
