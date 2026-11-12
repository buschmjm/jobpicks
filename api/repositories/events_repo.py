"""Append-only product event logging (plan §11)."""

from __future__ import annotations

import logging
import uuid
from typing import Any
from uuid import UUID

from core.database import SessionLocal
from core.models import Event, EventType
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def log_event(
    session: Session,
    *,
    event_type: EventType | str,
    user_id: UUID | None = None,
    entity_id: UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> Event:
    """Persist a single analytics event."""
    type_value = event_type.value if isinstance(event_type, EventType) else event_type
    event = Event(
        event_id=uuid.uuid4(),
        user_id=user_id,
        type=EventType(type_value),
        entity_id=entity_id,
        payload=payload,
    )
    session.add(event)
    return event


def log_event_standalone(
    *,
    event_type: EventType | str,
    user_id: UUID | None = None,
    entity_id: UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> Event | None:
    """Log an event in its own short-lived session (for stub services without DB deps)."""
    try:
        with SessionLocal() as session:
            event = log_event(
                session,
                event_type=event_type,
                user_id=user_id,
                entity_id=entity_id,
                payload=payload,
            )
            session.commit()
            return event
    except Exception:
        logger.exception("Failed to log event %s", event_type)
        return None


class EventsRepository:
    """Thin repository wrapper for append-only event logging."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def append(
        self,
        event_type: EventType | str,
        *,
        user_id: UUID | None = None,
        entity_id: UUID | None = None,
        payload: dict[str, Any] | None = None,
    ) -> Event:
        return log_event(
            self._session,
            event_type=event_type,
            user_id=user_id,
            entity_id=entity_id,
            payload=payload,
        )
