"""User job queue persistence."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from core.models import (
    FeedbackAction,
    FeedbackEvent,
    Job,
    QueueState,
    SwipeReason,
    UserJobQueue,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload


class DeckRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def count_queued(self, user_id: uuid.UUID) -> int:
        return int(
            self._session.scalar(
                select(func.count())
                .select_from(UserJobQueue)
                .where(UserJobQueue.user_id == user_id)
                .where(UserJobQueue.state == QueueState.QUEUED.value)
            )
            or 0
        )

    def get_next_queued(self, user_id: uuid.UUID) -> UserJobQueue | None:
        return self._session.scalar(
            select(UserJobQueue)
            .options(joinedload(UserJobQueue.job))
            .where(UserJobQueue.user_id == user_id)
            .where(UserJobQueue.state == QueueState.QUEUED.value)
            .order_by(UserJobQueue.score.desc().nullslast(), UserJobQueue.enqueued_at.asc())
            .limit(1)
        )

    def get_queue_item(self, user_id: uuid.UUID, queue_item_id: uuid.UUID) -> UserJobQueue | None:
        return self._session.scalar(
            select(UserJobQueue)
            .options(joinedload(UserJobQueue.job))
            .where(UserJobQueue.id == queue_item_id)
            .where(UserJobQueue.user_id == user_id)
        )

    def update_swipe_state(
        self,
        queue_item: UserJobQueue,
        *,
        state: QueueState,
        reason: SwipeReason | None = None,
    ) -> UserJobQueue:
        queue_item.state = state
        queue_item.reason = reason
        queue_item.swiped_at = datetime.now(UTC)
        self._session.flush()
        return queue_item

    def record_feedback(
        self,
        *,
        user_id: uuid.UUID,
        job_id: uuid.UUID,
        action: FeedbackAction,
        reason: SwipeReason | None = None,
        dwell_seconds: float | None = None,
        payload: dict[str, Any] | None = None,
    ) -> FeedbackEvent:
        row = FeedbackEvent(
            user_id=user_id,
            job_id=job_id,
            action=action.value,
            reason=reason.value if reason is not None else None,
            dwell_seconds=dwell_seconds,
            payload=payload,
        )
        self._session.add(row)
        self._session.flush()
        return row

    def get_job(self, job_id: uuid.UUID) -> Job | None:
        return self._session.get(Job, job_id)

    def list_queue_items(
        self,
        user_id: uuid.UUID,
        *,
        state: QueueState | None = None,
        remote_mode: str | None = None,
        min_salary: int | None = None,
        posted_within_days: int | None = None,
        keyword: str | None = None,
        limit: int = 100,
    ) -> list[UserJobQueue]:
        stmt = (
            select(UserJobQueue)
            .options(joinedload(UserJobQueue.job))
            .where(UserJobQueue.user_id == user_id)
            .order_by(UserJobQueue.enqueued_at.desc())
            .limit(limit)
        )
        if state is not None:
            stmt = stmt.where(UserJobQueue.state == state.value)
        rows = list(self._session.scalars(stmt).unique().all())

        if remote_mode or min_salary or posted_within_days or keyword:
            filtered: list[UserJobQueue] = []
            keyword_lower = keyword.lower() if keyword else None
            cutoff = None
            if posted_within_days is not None:
                cutoff = datetime.now(UTC) - timedelta(days=posted_within_days)
            for item in rows:
                job = item.job
                if job is None:
                    continue
                if remote_mode and job.remote_mode.value != remote_mode:
                    continue
                if min_salary is not None:
                    effective = job.salary_max or job.salary_min
                    if effective is not None and effective < min_salary:
                        continue
                if cutoff is not None and job.first_seen < cutoff:
                    continue
                if keyword_lower:
                    blob = f"{job.title} {job.description or ''} {job.company_name}".lower()
                    if keyword_lower not in blob:
                        continue
                filtered.append(item)
            return filtered
        return rows
