"""Resume builder message persistence."""

from __future__ import annotations

import uuid

from core.models import ResumeBuilderMessage
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

MAX_MESSAGES_PER_THREAD = 40


class ResumeMessageRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_messages(
        self,
        user_id: uuid.UUID,
        variant_id: uuid.UUID | None = None,
        *,
        limit: int = MAX_MESSAGES_PER_THREAD,
    ) -> list[ResumeBuilderMessage]:
        stmt = (
            select(ResumeBuilderMessage)
            .where(ResumeBuilderMessage.user_id == user_id)
            .order_by(ResumeBuilderMessage.created_at.asc())
            .limit(limit)
        )
        if variant_id is None:
            stmt = stmt.where(ResumeBuilderMessage.variant_id.is_(None))
        else:
            stmt = stmt.where(ResumeBuilderMessage.variant_id == variant_id)
        return list(self._session.scalars(stmt))

    def add_message(
        self,
        user_id: uuid.UUID,
        *,
        role: str,
        content: str,
        variant_id: uuid.UUID | None = None,
        proposal_id: uuid.UUID | None = None,
        source: str | None = None,
        status: str | None = None,
    ) -> ResumeBuilderMessage:
        row = ResumeBuilderMessage(
            user_id=user_id,
            variant_id=variant_id,
            role=role,
            content=content,
            proposal_id=proposal_id,
            source=source,
            status=status,
        )
        self._session.add(row)
        self._session.flush()
        self._trim_history(user_id, variant_id)
        return row

    def update_message(
        self,
        message_id: uuid.UUID,
        *,
        content: str | None = None,
        source: str | None = None,
        status: str | None = None,
        proposal_id: uuid.UUID | None = None,
    ) -> ResumeBuilderMessage | None:
        row = self._session.get(ResumeBuilderMessage, message_id)
        if row is None:
            return None
        if content is not None:
            row.content = content
        if source is not None:
            row.source = source
        if status is not None:
            row.status = status
        if proposal_id is not None:
            row.proposal_id = proposal_id
        self._session.flush()
        return row

    def _trim_history(self, user_id: uuid.UUID, variant_id: uuid.UUID | None) -> None:
        filters = [ResumeBuilderMessage.user_id == user_id]
        if variant_id is None:
            filters.append(ResumeBuilderMessage.variant_id.is_(None))
        else:
            filters.append(ResumeBuilderMessage.variant_id == variant_id)
        count = int(
            self._session.scalar(
                select(func.count()).select_from(ResumeBuilderMessage).where(*filters)
            )
            or 0
        )
        if count <= MAX_MESSAGES_PER_THREAD:
            return
        excess = count - MAX_MESSAGES_PER_THREAD
        oldest_ids = list(
            self._session.scalars(
                select(ResumeBuilderMessage.id)
                .where(*filters)
                .order_by(ResumeBuilderMessage.created_at.asc())
                .limit(excess)
            )
        )
        if oldest_ids:
            self._session.execute(
                delete(ResumeBuilderMessage).where(ResumeBuilderMessage.id.in_(oldest_ids))
            )

    def clear_messages(self, user_id: uuid.UUID, variant_id: uuid.UUID | None = None) -> int:
        stmt = delete(ResumeBuilderMessage).where(ResumeBuilderMessage.user_id == user_id)
        if variant_id is None:
            stmt = stmt.where(ResumeBuilderMessage.variant_id.is_(None))
        else:
            stmt = stmt.where(ResumeBuilderMessage.variant_id == variant_id)
        result = self._session.execute(stmt)
        return int(getattr(result, "rowcount", 0) or 0)
