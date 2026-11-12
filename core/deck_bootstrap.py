"""Deck population helpers: corpus checks and backfill scheduling."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.job_retention import open_corpus_filter
from core.models import Job, JobStatus, Profile, QueueJob, QueueJobStatus, QueueState, UserJobQueue
from core.queue_builder import CORPUS_WINDOW_DAYS

_BACKFILL_JOB_TYPE = "queue_backfill"
_CORPUS_INGEST_JOB_TYPE = "corpus_ingest"
_BACKFILL_AUTO_HEAL_MINUTES = 15

EnqueueFn = Callable[..., Any]


def open_job_count(session: Session, *, window_days: int = CORPUS_WINDOW_DAYS) -> int:
    _ = window_days
    return int(
        session.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.status == JobStatus.OPEN.value)
            .where(open_corpus_filter())
        )
        or 0
    )


def queued_count(session: Session, user_id: uuid.UUID) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(UserJobQueue)
            .where(UserJobQueue.user_id == user_id)
            .where(UserJobQueue.state == QueueState.QUEUED.value)
        )
        or 0
    )


def has_global_job_pending(session: Session, job_type: str) -> bool:
    row = session.scalar(
        select(QueueJob.id)
        .where(QueueJob.job_type == job_type)
        .where(
            QueueJob.status.in_(
                [QueueJobStatus.PENDING.value, QueueJobStatus.RUNNING.value]
            )
        )
        .limit(1)
    )
    return row is not None


def has_pending_backfill(session: Session, user_id: uuid.UUID) -> bool:
    uid = str(user_id)
    row = session.scalar(
        select(QueueJob.id)
        .where(QueueJob.job_type == _BACKFILL_JOB_TYPE)
        .where(
            QueueJob.status.in_(
                [QueueJobStatus.PENDING.value, QueueJobStatus.RUNNING.value]
            )
        )
        .where(QueueJob.payload["user_id"].as_string() == uid)
        .limit(1)
    )
    return row is not None


def has_pending_corpus_ingest(session: Session) -> bool:
    return has_global_job_pending(session, _CORPUS_INGEST_JOB_TYPE)


def recent_backfill_completed(
    session: Session,
    user_id: uuid.UUID,
    *,
    within_minutes: int = _BACKFILL_AUTO_HEAL_MINUTES,
) -> bool:
    profile = session.scalar(select(Profile).where(Profile.user_id == user_id))
    if (
        profile is not None
        and profile.last_backfill_at is not None
        and profile.last_backfill_at >= datetime.now(tz=UTC) - timedelta(minutes=within_minutes)
    ):
        return True

    uid = str(user_id)
    cutoff = datetime.now(tz=UTC) - timedelta(minutes=within_minutes)
    row = session.scalar(
        select(QueueJob.id)
        .where(QueueJob.job_type == _BACKFILL_JOB_TYPE)
        .where(QueueJob.payload["user_id"].as_string() == uid)
        .where(QueueJob.status == QueueJobStatus.COMPLETED.value)
        .where(QueueJob.finished_at >= cutoff)
        .limit(1)
    )
    return row is not None


def ensure_corpus_ingest(session: Session, *, enqueue: EnqueueFn) -> bool:
    """Insert at most one pending/running corpus_ingest job."""
    if has_global_job_pending(session, _CORPUS_INGEST_JOB_TYPE):
        return False
    enqueue(session, _CORPUS_INGEST_JOB_TYPE, {}, priority=10)
    return True


def fan_out_pending_backfills(session: Session, *, enqueue: EnqueueFn) -> int:
    """Enqueue queue_backfill for profiles awaiting deck population after ingest."""
    profiles = session.scalars(
        select(Profile)
        .where(Profile.awaiting_deck_backfill.is_(True))
        .where(Profile.onboarding_completed_at.is_not(None))
    ).all()
    count = 0
    for profile in profiles:
        if has_pending_backfill(session, profile.user_id):
            continue
        enqueue(
            session,
            _BACKFILL_JOB_TYPE,
            {"user_id": str(profile.user_id)},
            priority=5,
        )
        count += 1
    return count


def clear_awaiting_backfill(session: Session, user_id: uuid.UUID) -> None:
    profile = session.scalar(select(Profile).where(Profile.user_id == user_id))
    if profile is None:
        return
    profile.awaiting_deck_backfill = False
    profile.last_backfill_at = datetime.now(tz=UTC)


def schedule_backfill_if_needed(
    session: Session,
    user_id: uuid.UUID,
    *,
    enqueue: EnqueueFn,
) -> bool:
    """Enqueue backfill when the user has an empty deck and corpus exists."""
    if has_pending_backfill(session, user_id):
        return False
    if queued_count(session, user_id) > 0:
        return False
    if open_job_count(session) == 0:
        return False
    # Empty deck after backfill usually means corpus wasn't ready yet; retry after
    # a short cooldown so status polling does not enqueue duplicates constantly.
    if recent_backfill_completed(session, user_id) and recent_backfill_completed(
        session, user_id, within_minutes=2
    ):
        return False
    enqueue(session, _BACKFILL_JOB_TYPE, {"user_id": str(user_id)}, priority=5)
    return True
