"""Apply To-Do list service — DB-backed todo_items."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from core.models import EventType, Job, RemoteMode
from core.models import TodoItem as TodoItemModel
from core.models import TodoStatus as DbTodoStatus
from sqlalchemy.orm import Session

from api.repositories.deck_repo import DeckRepository
from api.repositories.events_repo import EventsRepository
from api.repositories.profile_repo import ProfileRepository
from api.repositories.todo_repo import TodoRepository
from api.schemas import ApplicationStep, MatchCard, TodoStatus, WorkMode
from api.schemas import TodoItem as TodoItemSchema
from api.services.application_steps import (
    normalize_steps,
    progress_summary,
    steps_from_template,
)


def _notify_preference_feedback(
    session: Session, user_id: UUID, job_id: UUID, status: TodoStatus
) -> None:
    """Update learned preferences when a todo is applied or archived."""
    from api.services.deck_service import deck_service

    if status == TodoStatus.applied:
        deck_service.record_todo_applied(session, user_id, job_id)
    elif status == TodoStatus.archived:
        deck_service.record_todo_archived(session, user_id, job_id)


def _format_salary(job: Job) -> str:
    if job.salary_min is None and job.salary_max is None:
        return "salary not listed"
    if job.salary_min is not None and job.salary_max is not None:
        return f"${job.salary_min // 1000}–{job.salary_max // 1000}k"
    if job.salary_min is not None:
        return f"${job.salary_min // 1000}k+"
    return f"up to ${job.salary_max // 1000}k"  # type: ignore[operator]


def _work_mode(remote_mode: RemoteMode | str) -> WorkMode:
    value = remote_mode.value if hasattr(remote_mode, "value") else str(remote_mode)
    try:
        return WorkMode(value)
    except ValueError:
        return WorkMode.unknown


def _steps_for_item(item: TodoItemModel) -> list[dict[str, object]]:
    raw = item.application_steps or []
    if not raw:
        return steps_from_template(None)
    return normalize_steps(raw)


def _packet_status_for_item(item: TodoItemModel) -> str:
    packet = item.application_packet
    if packet is None:
        return "none"
    status = packet.status.value if hasattr(packet.status, "value") else str(packet.status)
    if status in {"generating", "ready", "opened", "applied", "failed"}:
        return status
    return "none"


def todo_item_from_orm(item: TodoItemModel, queue_score: float | None = None) -> TodoItemSchema:
    job: Job | None = item.job
    match_score = None
    if queue_score is not None:
        match_score = int(round(float(queue_score) * 100))
    elif job is not None:
        match_score = None

    title = job.title if job else "Job"
    company = job.company_name if job else "Unknown"
    salary_display = _format_salary(job) if job else "salary not listed"
    work_mode = _work_mode(job.remote_mode) if job else WorkMode.unknown
    location_display = (job.location_text or "—") if job else "—"
    source_url = (job.source_url or "https://example.com") if job else "https://example.com"

    status_map = {
        DbTodoStatus.TO_APPLY.value: TodoStatus.to_apply,
        DbTodoStatus.APPLIED.value: TodoStatus.applied,
        DbTodoStatus.ARCHIVED.value: TodoStatus.archived,
    }
    status_value = item.status.value if hasattr(item.status, "value") else item.status
    steps = _steps_for_item(item)
    steps_done, steps_total = progress_summary(steps)

    return TodoItemSchema(
        id=item.id,
        job_id=item.job_id,
        status=status_map.get(status_value, TodoStatus.to_apply),
        match_score=match_score,
        title=title,
        company=company,
        salary_display=salary_display,
        work_mode=work_mode,
        location_display=location_display,
        source_url=source_url,
        created_at=item.created_at,
        updated_at=item.updated_at,
        applied_clicked_at=None,
        applied_selfreport_at=item.applied_at,
        application_steps=[ApplicationStep.model_validate(step) for step in steps],
        steps_done=steps_done,
        steps_total=steps_total,
        packet_status=_packet_status_for_item(item),  # type: ignore[arg-type]
        packet_id=item.application_packet.id if item.application_packet is not None else None,
    )


class TodoService:
    def list_items(
        self, session: Session, user_id: UUID, status: TodoStatus | None = None
    ) -> list[TodoItemSchema]:
        repo = TodoRepository(session)
        db_status = status.value if status else None
        return [todo_item_from_orm(item) for item in repo.list_items(user_id, db_status)]

    def get_item(self, session: Session, user_id: UUID, item_id: UUID) -> TodoItemSchema | None:
        item = TodoRepository(session).get_item(user_id, item_id)
        return todo_item_from_orm(item) if item else None

    def add_from_swipe(
        self,
        session: Session,
        user_id: UUID,
        card: MatchCard,
        *,
        commit: bool = False,
    ) -> TodoItemSchema:
        return self.ensure_apply_for_job(session, user_id, card, commit=commit)

    def ensure_apply_for_job(
        self,
        session: Session,
        user_id: UUID,
        card: MatchCard,
        *,
        commit: bool = False,
    ) -> TodoItemSchema:
        repo = TodoRepository(session)
        existing = repo.get_by_user_job(user_id, card.job_id)
        if existing is not None:
            status_value = existing.status.value if hasattr(existing.status, "value") else existing.status
            if status_value == DbTodoStatus.ARCHIVED.value:
                updated = repo.update_status(existing, DbTodoStatus.TO_APPLY.value)
                item = updated
            else:
                item = existing
        else:
            item = repo.create(user_id, card.job_id)
            EventsRepository(session).append(
                EventType.TODO_ADDED,
                user_id=user_id,
                entity_id=item.id,
                payload={"job_id": str(card.job_id)},
            )
        if commit:
            session.commit()
        refreshed = repo.get_item(user_id, item.id) or item
        return todo_item_from_orm(refreshed, queue_score=card.match_score / 100.0)

    def archive_for_job(self, session: Session, user_id: UUID, job_id: UUID) -> None:
        repo = TodoRepository(session)
        item = repo.get_by_user_job(user_id, job_id)
        if item is None:
            return
        status_value = item.status.value if hasattr(item.status, "value") else item.status
        if status_value == DbTodoStatus.ARCHIVED.value:
            return
        repo.update_status(item, DbTodoStatus.ARCHIVED.value)
        EventsRepository(session).append(
            EventType.TODO_ARCHIVED,
            user_id=user_id,
            entity_id=item.id,
            payload={"job_id": str(job_id), "change_decision": True},
        )
        _notify_preference_feedback(session, user_id, job_id, TodoStatus.archived)

    def create(self, session: Session, user_id: UUID, job_id: UUID) -> TodoItemSchema:
        repo = TodoRepository(session)
        if repo.get_job(job_id) is None and DeckRepository(session).get_job(job_id) is None:
            raise ValueError("Job not found")
        item = repo.create(user_id, job_id)
        EventsRepository(session).append(
            EventType.TODO_ADDED,
            user_id=user_id,
            entity_id=item.id,
            payload={"job_id": str(job_id)},
        )
        session.commit()
        refreshed = repo.get_item(user_id, item.id) or item
        return todo_item_from_orm(refreshed)

    def update_status(
        self, session: Session, user_id: UUID, item_id: UUID, status: TodoStatus
    ) -> TodoItemSchema | None:
        repo = TodoRepository(session)
        item = repo.get_item(user_id, item_id)
        if item is None:
            return None
        applied = status == TodoStatus.applied
        updated = repo.update_status(item, status.value, applied=applied)
        if status == TodoStatus.applied:
            EventsRepository(session).append(
                EventType.APPLIED_SELFREPORT,
                user_id=user_id,
                entity_id=item.id,
                payload={"did_apply": True, "source": "status_update"},
            )
            _notify_preference_feedback(session, user_id, item.job_id, TodoStatus.applied)
        elif status == TodoStatus.archived:
            EventsRepository(session).append(
                EventType.TODO_ARCHIVED,
                user_id=user_id,
                entity_id=item.id,
            )
            _notify_preference_feedback(session, user_id, item.job_id, TodoStatus.archived)
        session.commit()
        return todo_item_from_orm(updated)

    def update_item(
        self,
        session: Session,
        user_id: UUID,
        item_id: UUID,
        *,
        status: TodoStatus | None = None,
        application_steps: list[ApplicationStep] | None = None,
    ) -> TodoItemSchema | None:
        repo = TodoRepository(session)
        item = repo.get_item(user_id, item_id)
        if item is None:
            return None
        if application_steps is not None:
            repo.update_steps(
                item,
                [step.model_dump() for step in application_steps],
            )
        if status is not None:
            applied = status == TodoStatus.applied
            repo.update_status(item, status.value, applied=applied)
            if status == TodoStatus.applied:
                EventsRepository(session).append(
                    EventType.APPLIED_SELFREPORT,
                    user_id=user_id,
                    entity_id=item.id,
                    payload={"did_apply": True, "source": "status_update"},
                )
                _notify_preference_feedback(session, user_id, item.job_id, TodoStatus.applied)
            elif status == TodoStatus.archived:
                EventsRepository(session).append(
                    EventType.TODO_ARCHIVED,
                    user_id=user_id,
                    entity_id=item.id,
                )
                _notify_preference_feedback(session, user_id, item.job_id, TodoStatus.archived)
        session.commit()
        refreshed = repo.get_item(user_id, item_id) or item
        return todo_item_from_orm(refreshed)

    def update_steps(
        self,
        session: Session,
        user_id: UUID,
        item_id: UUID,
        steps: list[ApplicationStep],
    ) -> TodoItemSchema | None:
        repo = TodoRepository(session)
        item = repo.get_item(user_id, item_id)
        if item is None:
            return None
        repo.update_steps(item, [step.model_dump() for step in steps])
        session.commit()
        refreshed = repo.get_item(user_id, item_id) or item
        return todo_item_from_orm(refreshed)

    def get_step_template(self, session: Session, user_id: UUID) -> list[ApplicationStep]:
        profile = ProfileRepository(session).get_profile(user_id)
        template = profile.default_application_steps if profile else None
        return [ApplicationStep.model_validate(step) for step in steps_from_template(template)]

    def save_step_template(
        self,
        session: Session,
        user_id: UUID,
        steps: list[ApplicationStep],
    ) -> list[ApplicationStep]:
        profile_repo = ProfileRepository(session)
        profile = profile_repo.get_or_create_profile(user_id)
        normalized = normalize_steps([step.model_dump() for step in steps], allow_empty=False)
        profile.default_application_steps = normalized
        profile.updated_at = datetime.now(UTC)
        session.commit()
        return [ApplicationStep.model_validate(step) for step in normalized]

    def record_apply_click(
        self, session: Session, user_id: UUID, item_id: UUID
    ) -> TodoItemSchema | None:
        item = TodoRepository(session).get_item(user_id, item_id)
        if item is None:
            return None
        EventsRepository(session).append(
            EventType.APPLIED_CLICKED,
            user_id=user_id,
            entity_id=item.id,
            payload={"job_id": str(item.job_id)},
        )
        session.commit()
        schema = todo_item_from_orm(item)
        now = datetime.now(UTC)
        return schema.model_copy(update={"applied_clicked_at": now, "updated_at": now})

    def record_self_report(
        self, session: Session, user_id: UUID, item_id: UUID, did_apply: bool
    ) -> TodoItemSchema | None:
        repo = TodoRepository(session)
        item = repo.get_item(user_id, item_id)
        if item is None:
            return None
        now = datetime.now(UTC)
        if did_apply:
            repo.update_status(item, DbTodoStatus.APPLIED.value, applied=True)
            EventsRepository(session).append(
                EventType.APPLIED_SELFREPORT,
                user_id=user_id,
                entity_id=item.id,
                payload={"did_apply": True},
            )
            _notify_preference_feedback(session, user_id, item.job_id, TodoStatus.applied)
        else:
            EventsRepository(session).append(
                EventType.APPLIED_SELFREPORT,
                user_id=user_id,
                entity_id=item.id,
                payload={"did_apply": False},
            )
        session.commit()
        refreshed = repo.get_item(user_id, item_id) or item
        schema = todo_item_from_orm(refreshed)
        return schema.model_copy(update={"applied_selfreport_at": now, "updated_at": now})

    def delete(self, session: Session, user_id: UUID, item_id: UUID) -> bool:
        deleted = TodoRepository(session).delete(user_id, item_id)
        if deleted:
            session.commit()
        return deleted


todo_service = TodoService()
