"""Saved application answer vault service."""

from __future__ import annotations

import uuid

from core.apply.vault import normalize_question_key
from core.models import SavedApplicationAnswer
from sqlalchemy.orm import Session

from api.repositories.saved_application_answer_repo import SavedApplicationAnswerRepository
from api.schemas import (
    SavedApplicationAnswerListResponse,
    SavedApplicationAnswerResponse,
    SavedApplicationAnswerUpsertRequest,
)


def _to_response(row: SavedApplicationAnswer) -> SavedApplicationAnswerResponse:
    return SavedApplicationAnswerResponse(
        id=row.id,
        question_key=row.question_key,
        question_text=row.question_text,
        answer=row.answer,
        last_used_at=row.last_used_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SavedApplicationAnswerService:
    def list_answers(self, session: Session, user_id: uuid.UUID) -> SavedApplicationAnswerListResponse:
        rows = SavedApplicationAnswerRepository(session).list_for_user(user_id)
        return SavedApplicationAnswerListResponse(items=[_to_response(row) for row in rows])

    def upsert(
        self,
        session: Session,
        user_id: uuid.UUID,
        question_key: str,
        body: SavedApplicationAnswerUpsertRequest,
    ) -> SavedApplicationAnswerResponse:
        key = normalize_question_key(question_key)
        row = SavedApplicationAnswerRepository(session).upsert(
            user_id,
            question_key=key,
            question_text=body.question_text,
            answer=body.answer,
        )
        session.commit()
        session.refresh(row)
        return _to_response(row)

    def delete(self, session: Session, user_id: uuid.UUID, question_key: str) -> bool:
        deleted = SavedApplicationAnswerRepository(session).delete(user_id, question_key)
        if deleted:
            session.commit()
        return deleted


saved_application_answer_service = SavedApplicationAnswerService()
