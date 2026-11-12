"""Client and server instrumentation helpers (Workstream D)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from api.repositories.events_repo import log_event
from sqlalchemy.orm import Session

from core.models import EventType

CLIENT_EVENT_TYPES = frozenset(
    {
        EventType.CARD_VIEWED.value,
        EventType.LOGIN.value,
        EventType.PAGE_VIEW.value,
        EventType.DECK_OPENED.value,
        EventType.SETTINGS_OPENED.value,
    }
)


def track_client_event(
    session: Session,
    *,
    user_id: UUID,
    event_type: str,
    entity_id: UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    normalized = event_type.strip().lower()
    if normalized not in CLIENT_EVENT_TYPES:
        raise ValueError(f"Unsupported client event type: {event_type}")
    if normalized == EventType.LOGIN.value:
        stored_type = EventType.LOGIN
    elif normalized == EventType.CARD_VIEWED.value:
        stored_type = EventType.CARD_VIEWED
    elif normalized == EventType.PAGE_VIEW.value:
        stored_type = EventType.PAGE_VIEW
    elif normalized == EventType.DECK_OPENED.value:
        stored_type = EventType.DECK_OPENED
    elif normalized == EventType.SETTINGS_OPENED.value:
        stored_type = EventType.SETTINGS_OPENED
    else:
        raise ValueError(f"Unsupported client event type: {event_type}")
    log_event(
        session,
        event_type=stored_type,
        user_id=user_id,
        entity_id=entity_id,
        payload=payload,
    )
