"""Internal event logging helpers and digest open tracking."""

from __future__ import annotations

import os
from typing import Any
from uuid import UUID

from core.instrumentation import track_client_event
from core.models import Digest, EventType
from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.deps import get_current_user, get_db
from api.repositories.events_repo import log_event
from api.schemas import SessionUser, TrackEventResponse

router = APIRouter(prefix="/events", tags=["events"])


def require_internal_events_token(x_internal_token: str | None = Header(default=None)) -> None:
    expected = os.environ.get("INTERNAL_EVENTS_TOKEN")
    if not expected:
        if os.environ.get("APP_ENV", "development") == "development":
            expected = "dev-internal-events-token"
        else:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="INTERNAL_EVENTS_TOKEN not configured",
            )
    if x_internal_token != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal token")


class LogEventRequest(BaseModel):
    type: str
    user_id: UUID | None = None
    entity_id: UUID | None = None
    payload: dict[str, Any] | None = None


class TrackEventRequest(BaseModel):
    type: str
    entity_id: UUID | None = None
    payload: dict[str, Any] | None = None


@router.post("/log", status_code=status.HTTP_201_CREATED)
def internal_log_event(
    body: LogEventRequest,
    session: Session = Depends(get_db),
    _: None = Depends(require_internal_events_token),
) -> dict[str, str]:
    """Internal helper for workers to append analytics events."""
    event = log_event(
        session,
        event_type=body.type,
        user_id=body.user_id,
        entity_id=body.entity_id,
        payload=body.payload,
    )
    session.commit()
    return {"event_id": str(event.event_id)}


@router.post("/track", response_model=TrackEventResponse, status_code=status.HTTP_201_CREATED)
def track_client_event_route(
    body: TrackEventRequest,
    session: Session = Depends(get_db),
    user: SessionUser = Depends(get_current_user),
) -> TrackEventResponse:
    """Authenticated client instrumentation (Workstream D)."""
    try:
        track_client_event(
            session,
            user_id=user.id,
            event_type=body.type,
            entity_id=body.entity_id,
            payload=body.payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    session.commit()
    return TrackEventResponse(accepted=True)


@router.get("/digest/open/{tracking_token}")
def digest_open(tracking_token: str, session: Session = Depends(get_db)) -> RedirectResponse:
    """Track digest opens via redirect link (plan §13 — no pixel-only tracking)."""
    digest = session.query(Digest).filter(Digest.tracking_token == tracking_token).one_or_none()
    if digest is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Digest not found")

    from datetime import UTC, datetime

    if digest.opened_at is None:
        digest.opened_at = datetime.now(UTC)
        log_event(
            session,
            event_type=EventType.DIGEST_OPENED,
            user_id=digest.user_id,
            entity_id=digest.id,
            payload={"tracking_token": tracking_token},
        )
        session.commit()

    return RedirectResponse(url="/deck", status_code=status.HTTP_302_FOUND)
