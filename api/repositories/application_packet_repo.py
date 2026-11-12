"""Application packet persistence."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from core.models import ApplicationPacket, ApplicationPacketStatus
from sqlalchemy import select
from sqlalchemy.orm import Session


class ApplicationPacketRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_todo(
        self, user_id: uuid.UUID, todo_item_id: uuid.UUID
    ) -> ApplicationPacket | None:
        return self._session.scalar(
            select(ApplicationPacket)
            .where(ApplicationPacket.user_id == user_id)
            .where(ApplicationPacket.todo_item_id == todo_item_id)
        )

    def get_by_id(self, user_id: uuid.UUID, packet_id: uuid.UUID) -> ApplicationPacket | None:
        return self._session.scalar(
            select(ApplicationPacket)
            .where(ApplicationPacket.user_id == user_id)
            .where(ApplicationPacket.id == packet_id)
        )

    def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        prepared_only: bool = False,
    ) -> list[ApplicationPacket]:
        stmt = (
            select(ApplicationPacket)
            .where(ApplicationPacket.user_id == user_id)
            .order_by(ApplicationPacket.updated_at.desc())
        )
        if prepared_only:
            stmt = stmt.where(
                ApplicationPacket.status.in_(
                    [
                        ApplicationPacketStatus.READY.value,
                        ApplicationPacketStatus.OPENED.value,
                        ApplicationPacketStatus.APPLIED.value,
                    ]
                )
            )
        return list(self._session.scalars(stmt).all())

    def create(
        self,
        *,
        user_id: uuid.UUID,
        todo_item_id: uuid.UUID,
        job_id: uuid.UUID,
        apply_url: str,
        status: ApplicationPacketStatus | str = ApplicationPacketStatus.GENERATING,
        ats_type: str | None = None,
        label: str | None = None,
        fit_verdict: str | None = None,
        fit_rationale: list[Any] | None = None,
        identity: dict[str, Any] | None = None,
        resume_draft_id: uuid.UUID | None = None,
        resume_pdf_path: str | None = None,
        cover_letter: str | None = None,
        answers: list[Any] | None = None,
        generation_error: str | None = None,
    ) -> ApplicationPacket:
        status_value = status.value if isinstance(status, ApplicationPacketStatus) else status
        packet = ApplicationPacket(
            user_id=user_id,
            todo_item_id=todo_item_id,
            job_id=job_id,
            status=status_value,
            apply_url=apply_url,
            ats_type=ats_type,
            label=label,
            fit_verdict=fit_verdict,
            fit_rationale=fit_rationale or [],
            identity=identity or {},
            resume_draft_id=resume_draft_id,
            resume_pdf_path=resume_pdf_path,
            cover_letter=cover_letter,
            answers=answers or [],
            generation_error=generation_error,
        )
        self._session.add(packet)
        self._session.flush()
        return packet

    def update(self, packet: ApplicationPacket, **fields: Any) -> ApplicationPacket:
        now = datetime.now(UTC)
        for key, value in fields.items():
            if key == "status" and isinstance(value, ApplicationPacketStatus):
                value = value.value
            setattr(packet, key, value)
        packet.updated_at = now
        self._session.flush()
        return packet

    def upsert_for_todo(
        self,
        *,
        user_id: uuid.UUID,
        todo_item_id: uuid.UUID,
        job_id: uuid.UUID,
        apply_url: str,
        **fields: Any,
    ) -> ApplicationPacket:
        existing = self.get_by_todo(user_id, todo_item_id)
        if existing is not None:
            return self.update(
                existing,
                job_id=job_id,
                apply_url=apply_url,
                **fields,
            )
        return self.create(
            user_id=user_id,
            todo_item_id=todo_item_id,
            job_id=job_id,
            apply_url=apply_url,
            **fields,
        )
