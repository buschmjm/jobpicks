"""Postgres queue consumer (SELECT FOR UPDATE SKIP LOCKED on queue_jobs)."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from core.database import SessionLocal
from core.deck_bootstrap import clear_awaiting_backfill, fan_out_pending_backfills
from core.models import QueueJob, QueueJobStatus
from core.queue_builder import QueueBuilder, SqlAlchemyQueueBuilderStore
from sqlalchemy import select, update
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

JobHandler = Callable[[Session, dict[str, Any]], None]

HANDLERS: dict[str, JobHandler] = {}


def register_handler(job_type: str, handler: JobHandler) -> None:
    HANDLERS[job_type] = handler


def _handle_backfill(session: Session, payload: dict[str, Any]) -> None:
    user_id = uuid.UUID(payload["user_id"])
    builder = QueueBuilder(SqlAlchemyQueueBuilderStore(session))
    total = 0
    for chunk_size in builder.backfill_user_batched(user_id):
        total += chunk_size
        session.commit()
    clear_awaiting_backfill(session, user_id)
    logger.info("backfill complete user=%s enqueued=%d", user_id, total)


register_handler("queue_backfill", _handle_backfill)


def _handle_corpus_ingest(session: Session, payload: dict[str, Any]) -> None:
    """Pull shared job corpus once, then fan out DB-only backfills."""
    from ingest.runner import run_ingest

    _ = payload
    stats = run_ingest(session)
    logger.info("corpus ingest complete stats=%s", stats)
    enqueue_job(session, "cron_normalize_embed", {})
    enqueued = fan_out_pending_backfills(session, enqueue=enqueue_job)
    logger.info("corpus ingest fan-out backfills=%d", enqueued)


register_handler("corpus_ingest", _handle_corpus_ingest)


def _handle_term_ingest(session: Session, payload: dict[str, Any]) -> None:
    """Fetch jobs for newly registered target titles, then backfill the user deck."""
    from ingest.runner import run_term_ingest

    raw_terms = payload.get("terms") or []
    terms = tuple(str(term) for term in raw_terms if str(term).strip())
    user_id = payload.get("user_id")
    if not terms:
        logger.info("term_ingest skipped: no terms in payload")
        return

    stats = run_term_ingest(session, terms)
    logger.info("term ingest complete stats=%s terms=%s", stats, terms)

    if stats.get("created", 0) + stats.get("updated", 0) > 0:
        enqueue_job(session, "cron_normalize_embed", {})

    if user_id:
        enqueue_job(session, "queue_backfill", {"user_id": str(user_id)}, priority=5)


register_handler("term_ingest", _handle_term_ingest)


def _handle_packet_prefetch(session: Session, payload: dict[str, Any]) -> None:
    """Background-generate application packet after swipe-right or job import."""
    from api.services.application_packet_service import application_packet_service

    user_id = uuid.UUID(payload["user_id"])
    todo_item_id = uuid.UUID(payload["todo_item_id"])
    try:
        application_packet_service.execute_generate(session, user_id, todo_item_id)
        session.commit()
        logger.info("packet prefetch complete user=%s todo=%s", user_id, todo_item_id)
    except Exception:
        logger.exception("packet prefetch failed user=%s todo=%s", user_id, todo_item_id)
        session.rollback()


register_handler("packet_prefetch", _handle_packet_prefetch)


def _handle_cron_normalize_embed(session: Session, payload: dict[str, Any]) -> None:
    _ = session, payload
    from workers.jobs import normalize_embed

    normalize_embed.main()


def _handle_cron_score(session: Session, payload: dict[str, Any]) -> None:
    _ = session, payload
    from workers.jobs import score

    score.main()


def _handle_cron_queue_topup(session: Session, payload: dict[str, Any]) -> None:
    _ = session, payload
    from workers.jobs import queue_topup

    queue_topup.main()


register_handler("cron_normalize_embed", _handle_cron_normalize_embed)
register_handler("cron_score", _handle_cron_score)
register_handler("cron_queue_topup", _handle_cron_queue_topup)


def claim_next_job(session: Session) -> QueueJob | None:
    """Claim one pending queue job using SKIP LOCKED."""
    now = datetime.now(tz=UTC)
    stmt = (
        select(QueueJob)
        .where(QueueJob.status == QueueJobStatus.PENDING.value)
        .where(QueueJob.scheduled_at <= now)
        .order_by(QueueJob.priority.desc(), QueueJob.scheduled_at.asc())
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    job = session.scalar(stmt)
    if job is None:
        return None

    job.status = QueueJobStatus.RUNNING
    job.started_at = now
    job.attempts += 1
    session.flush()
    return job


def complete_job(session: Session, job: QueueJob) -> None:
    job.status = QueueJobStatus.COMPLETED
    job.finished_at = datetime.now(tz=UTC)
    job.last_error = None


def fail_job(session: Session, job: QueueJob, error: str) -> None:
    now = datetime.now(tz=UTC)
    job.last_error = error[:4000]
    if job.attempts >= job.max_attempts:
        job.status = QueueJobStatus.FAILED
        job.finished_at = now
    else:
        job.status = QueueJobStatus.PENDING
        job.started_at = None


def dispatch_job(session: Session, job: QueueJob) -> None:
    handler = HANDLERS.get(job.job_type)
    if handler is None:
        raise ValueError(f"no handler registered for job_type={job.job_type!r}")
    handler(session, job.payload or {})


_LLM_HEAVY_JOB_TYPES = frozenset(
    {
        "cron_normalize_embed",
        "packet_prefetch",
        "corpus_ingest",
    }
)


def process_one(session: Session | None = None) -> bool:
    """Process a single queue job. Returns True if a job was processed."""
    own_session = session is None
    session = session or SessionLocal()
    worker_slot = False
    try:
        job = claim_next_job(session)
        if job is None:
            if own_session:
                session.commit()
            return False

        if job.job_type in _LLM_HEAVY_JOB_TYPES:
            from inference.load_control import defer_worker_llm_job, try_worker_llm_slot

            if not try_worker_llm_slot(session):
                defer_worker_llm_job(session, job.id)
                session.commit()
                return True
            worker_slot = True

        try:
            dispatch_job(session, job)
            complete_job(session, job)
        except Exception:
            logger.exception("queue job %s failed", job.id)
            fail_job(session, job, "handler error")
        session.commit()
        return True
    except Exception:
        session.rollback()
        raise
    finally:
        if worker_slot:
            from inference.load_control import release_worker_llm_slot

            release_worker_llm_slot(session)
        if own_session:
            session.close()


def run_consumer(*, poll: bool = True, idle_sleep_seconds: float = 1.0) -> None:
    """Run the queue consumer loop.

    poll=True (default): long-running daemon; sleep when the queue is empty.
    poll=False: drain pending jobs once, then exit.
    """
    logger.info("starting queue consumer")
    with SessionLocal() as session:
        requeued = requeue_stale_running(session, older_than_minutes=5)
        if requeued:
            logger.info("requeued %d stale running queue jobs", requeued)
        from api.services.application_packet_service import application_packet_service

        recovered = application_packet_service.recover_stale_generating(session)
        if recovered:
            logger.info("re-queued %d stale generating application packets", recovered)
        session.commit()

    while True:
        processed = process_one()
        if not processed:
            if poll:
                time.sleep(idle_sleep_seconds)
            else:
                break


def enqueue_job(
    session: Session,
    job_type: str,
    payload: dict[str, Any],
    *,
    priority: int = 0,
    scheduled_at: datetime | None = None,
) -> QueueJob:
    """Insert a new queue_jobs row."""
    row = QueueJob(
        job_type=job_type,
        payload=payload,
        priority=priority,
        scheduled_at=scheduled_at or datetime.now(tz=UTC),
    )
    session.add(row)
    session.flush()
    return row


def requeue_stale_running(session: Session, *, older_than_minutes: int = 30) -> int:
    """Reset stuck RUNNING jobs back to PENDING (operational safety)."""
    cutoff = datetime.now(tz=UTC) - timedelta(minutes=older_than_minutes)
    stmt = (
        update(QueueJob)
        .where(QueueJob.status == QueueJobStatus.RUNNING.value)
        .where(QueueJob.started_at < cutoff)
        .values(status=QueueJobStatus.PENDING.value, started_at=None)
    )
    from sqlalchemy.engine import CursorResult

    result = session.execute(stmt)
    if isinstance(result, CursorResult):
        return result.rowcount or 0
    return 0

