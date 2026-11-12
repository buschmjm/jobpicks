"""Career advisor message persistence."""

from __future__ import annotations

import uuid
from typing import Any

from core.models import CareerMessage
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

MAX_MESSAGES_PER_USER = 40


class CareerMessageRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_messages(self, user_id: uuid.UUID, *, limit: int = 40) -> list[CareerMessage]:
        return list(
            self._session.scalars(
                select(CareerMessage)
                .where(CareerMessage.user_id == user_id)
                .order_by(CareerMessage.created_at.asc())
                .limit(limit)
            )
        )

    def add_message(
        self,
        user_id: uuid.UUID,
        *,
        role: str,
        content: str,
        source: str | None = None,
        status: str | None = None,
        sources: list[dict[str, Any]] | None = None,
    ) -> CareerMessage:
        row = CareerMessage(
            user_id=user_id,
            role=role,
            content=content,
            source=source,
            status=status,
            sources=sources,
        )
        self._session.add(row)
        self._session.flush()
        self._trim_history(user_id)
        return row

    def update_message(
        self,
        message_id: uuid.UUID,
        *,
        content: str | None = None,
        source: str | None = None,
        status: str | None = None,
        sources: list[dict[str, Any]] | None = None,
    ) -> CareerMessage | None:
        row = self._session.get(CareerMessage, message_id)
        if row is None:
            return None
        if content is not None:
            row.content = content
        if source is not None:
            row.source = source
        if status is not None:
            row.status = status
        if sources is not None:
            row.sources = sources
        self._session.flush()
        return row

    def _trim_history(self, user_id: uuid.UUID) -> None:
        count = int(
            self._session.scalar(
                select(func.count())
                .select_from(CareerMessage)
                .where(CareerMessage.user_id == user_id)
            )
            or 0
        )
        if count <= MAX_MESSAGES_PER_USER:
            return
        excess = count - MAX_MESSAGES_PER_USER
        oldest_ids = list(
            self._session.scalars(
                select(CareerMessage.id)
                .where(CareerMessage.user_id == user_id)
                .order_by(CareerMessage.created_at.asc())
                .limit(excess)
            )
        )
        if oldest_ids:
            self._session.execute(delete(CareerMessage).where(CareerMessage.id.in_(oldest_ids)))

    def clear_messages(self, user_id: uuid.UUID) -> int:
        result = self._session.execute(
            delete(CareerMessage).where(CareerMessage.user_id == user_id)
        )
        return int(getattr(result, "rowcount", 0) or 0)
