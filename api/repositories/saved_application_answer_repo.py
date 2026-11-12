"""Saved application answer vault persistence."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from core.apply.vault import normalize_question_key
from core.models import SavedApplicationAnswer
from sqlalchemy import select
from sqlalchemy.orm import Session


class SavedApplicationAnswerRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_user(self, user_id: uuid.UUID) -> list[SavedApplicationAnswer]:
        return list(
            self._session.scalars(
                select(SavedApplicationAnswer)
                .where(SavedApplicationAnswer.user_id == user_id)
                .order_by(SavedApplicationAnswer.last_used_at.desc())
            ).all()
        )

    def get_by_key(self, user_id: uuid.UUID, question_key: str) -> SavedApplicationAnswer | None:
        key = normalize_question_key(question_key)
        if not key:
            return None
        return self._session.scalar(
            select(SavedApplicationAnswer)
            .where(SavedApplicationAnswer.user_id == user_id)
            .where(SavedApplicationAnswer.question_key == key)
        )

    def upsert(
        self,
        user_id: uuid.UUID,
        *,
        question_key: str,
        question_text: str,
        answer: str,
        touch_used: bool = True,
    ) -> SavedApplicationAnswer:
        key = normalize_question_key(question_key)
        if not key:
            raise ValueError("Invalid question key")
        text = (question_text or key.replace("_", " ").title()).strip()
        value = (answer or "").strip()
        if not value:
            raise ValueError("Answer cannot be empty")

        now = datetime.now(UTC)
        existing = self.get_by_key(user_id, key)
        if existing is not None:
            existing.question_text = text[:2000]
            existing.answer = value[:4000]
            existing.updated_at = now
            if touch_used:
                existing.last_used_at = now
            self._session.flush()
            return existing

        row = SavedApplicationAnswer(
            user_id=user_id,
            question_key=key,
            question_text=text[:2000],
            answer=value[:4000],
            last_used_at=now,
        )
        self._session.add(row)
        self._session.flush()
        return row

    def delete(self, user_id: uuid.UUID, question_key: str) -> bool:
        row = self.get_by_key(user_id, question_key)
        if row is None:
            return False
        self._session.delete(row)
        self._session.flush()
        return True

    def touch_keys(self, user_id: uuid.UUID, keys: list[str]) -> None:
        now = datetime.now(UTC)
        normalized = {normalize_question_key(k) for k in keys if normalize_question_key(k)}
        if not normalized:
            return
        rows = self._session.scalars(
            select(SavedApplicationAnswer)
            .where(SavedApplicationAnswer.user_id == user_id)
            .where(SavedApplicationAnswer.question_key.in_(normalized))
        ).all()
        for row in rows:
            row.last_used_at = now
        self._session.flush()
