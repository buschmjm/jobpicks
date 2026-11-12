"""Todo item persistence."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from core.models import Job, TodoItem, TodoStatus
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from api.repositories.profile_repo import ProfileRepository
from api.services.application_steps import normalize_steps, steps_from_template


class TodoRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_items(
        self, user_id: uuid.UUID, status: TodoStatus | str | None = None
    ) -> list[TodoItem]:
        stmt = (
            select(TodoItem)
            .options(joinedload(TodoItem.job), joinedload(TodoItem.application_packet))
            .where(TodoItem.user_id == user_id)
            .order_by(TodoItem.created_at.desc())
        )
        if status is not None:
            status_value = status.value if isinstance(status, TodoStatus) else status
            stmt = stmt.where(TodoItem.status == status_value)
        return list(self._session.scalars(stmt).all())

    def get_item(self, user_id: uuid.UUID, item_id: uuid.UUID) -> TodoItem | None:
        return self._session.scalar(
            select(TodoItem)
            .options(joinedload(TodoItem.job), joinedload(TodoItem.application_packet))
            .where(TodoItem.id == item_id)
            .where(TodoItem.user_id == user_id)
        )

    def get_by_user_job(self, user_id: uuid.UUID, job_id: uuid.UUID) -> TodoItem | None:
        return self._session.scalar(
            select(TodoItem)
            .options(joinedload(TodoItem.job), joinedload(TodoItem.application_packet))
            .where(TodoItem.user_id == user_id)
            .where(TodoItem.job_id == job_id)
        )

    def create(self, user_id: uuid.UUID, job_id: uuid.UUID) -> TodoItem:
        existing = self.get_by_user_job(user_id, job_id)
        if existing is not None:
            return existing
        profile = ProfileRepository(self._session).get_profile(user_id)
        template = profile.default_application_steps if profile else None
        item = TodoItem(
            user_id=user_id,
            job_id=job_id,
            status=TodoStatus.TO_APPLY.value,
            application_steps=steps_from_template(template),
        )
        self._session.add(item)
        self._session.flush()
        return self._session.scalar(
            select(TodoItem)
            .options(joinedload(TodoItem.job))
            .where(TodoItem.id == item.id)
        ) or item

    def update_steps(self, item: TodoItem, steps: list[dict[str, object]]) -> TodoItem:
        item.application_steps = normalize_steps(steps)
        item.updated_at = datetime.now(UTC)
        self._session.flush()
        return item

    def update_status(
        self, item: TodoItem, status: TodoStatus | str, *, applied: bool = False
    ) -> TodoItem:
        status_value = status.value if isinstance(status, TodoStatus) else status
        status_enum = status if isinstance(status, TodoStatus) else TodoStatus(status_value)
        now = datetime.now(UTC)
        item.status = status_enum
        item.updated_at = now
        if applied:
            item.applied_at = now
        elif status_value == TodoStatus.TO_APPLY.value:
            item.applied_at = None
        if status_value == TodoStatus.ARCHIVED.value:
            item.archived_at = now
        self._session.flush()
        return item

    def delete(self, user_id: uuid.UUID, item_id: uuid.UUID) -> bool:
        item = self.get_item(user_id, item_id)
        if item is None:
            return False
        self._session.delete(item)
        self._session.flush()
        return True

    def get_job(self, job_id: uuid.UUID) -> Job | None:
        return self._session.get(Job, job_id)
