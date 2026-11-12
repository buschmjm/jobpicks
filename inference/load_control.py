"""LLM load control: advisory locks, FIFO depth, rate limits (A4)."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from inference.config import (
    advisor_fifo_busy_depth,
    advisor_rate_limit_per_min,
    builder_rate_limit_per_min,
)

logger = logging.getLogger(__name__)

# Session-level Postgres advisory lock key for interactive LLM work.
INTERACTIVE_ADVISORY_KEY = 0x4A44_E001

_advisor_fifo_lock = threading.Lock()
_advisor_fifo_depth = 0


@dataclass
class RateLimiter:
    max_requests: int
    window_seconds: int
    _windows: dict[str, tuple[int, float]] = field(default_factory=dict)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        count, window_start = self._windows.get(key, (0, now))
        if now - window_start >= self.window_seconds:
            count, window_start = 0, now
        if count >= self.max_requests:
            return False
        self._windows[key] = (count + 1, window_start)
        return True


_advisor_rate = RateLimiter(max_requests=advisor_rate_limit_per_min(), window_seconds=60)
_builder_rate = RateLimiter(max_requests=builder_rate_limit_per_min(), window_seconds=60)


def check_advisor_rate_limit(user_id: uuid.UUID) -> bool:
    return _advisor_rate.allow(str(user_id))


def check_builder_rate_limit(user_id: uuid.UUID) -> bool:
    return _builder_rate.allow(str(user_id))


def begin_advisor_fifo() -> Literal["proceed", "busy"]:
    """Return busy when more than configured requests are already queued."""
    global _advisor_fifo_depth
    limit = advisor_fifo_busy_depth()
    with _advisor_fifo_lock:
        if _advisor_fifo_depth >= limit:
            return "busy"
        _advisor_fifo_depth += 1
        return "proceed"


def end_advisor_fifo() -> None:
    global _advisor_fifo_depth
    with _advisor_fifo_lock:
        _advisor_fifo_depth = max(0, _advisor_fifo_depth - 1)


BUSY_ADVISOR_REPLY = (
    "I'm handling several conversations right now. Please try again in a moment — "
    "your message is saved and I'll be ready shortly."
)


@contextmanager
def interactive_llm_lock(session: Session) -> Iterator[bool]:
    """
    Acquire the interactive advisory lock for the DB session lifetime.
    Yields True when acquired, False when another interactive generation holds it.
    """
    bind = session.get_bind()
    if bind.dialect.name == "sqlite":
        yield True
        return

    acquired = bool(
        session.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": INTERACTIVE_ADVISORY_KEY})
    )
    try:
        yield acquired
    finally:
        if acquired:
            session.scalar(text("SELECT pg_advisory_unlock(:key)"), {"key": INTERACTIVE_ADVISORY_KEY})


def try_worker_llm_slot(session: Session) -> bool:
    """
    Workers acquire the same advisory lock before LLM-heavy jobs.
    Returns False when interactive generation is in flight.
    """
    bind = session.get_bind()
    if bind.dialect.name == "sqlite":
        return True
    return bool(
        session.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": INTERACTIVE_ADVISORY_KEY})
    )


def release_worker_llm_slot(session: Session) -> None:
    bind = session.get_bind()
    if bind.dialect.name == "sqlite":
        return
    session.scalar(text("SELECT pg_advisory_unlock(:key)"), {"key": INTERACTIVE_ADVISORY_KEY})


def defer_worker_llm_job(session: Session, job_id: uuid.UUID, *, delay_seconds: int = 30) -> None:
    from datetime import UTC, datetime, timedelta

    from core.models import QueueJob, QueueJobStatus

    row = session.get(QueueJob, job_id)
    if row is None:
        return
    row.scheduled_at = datetime.now(UTC) + timedelta(seconds=delay_seconds)
    row.status = QueueJobStatus.PENDING
    session.flush()
    logger.info("deferred worker llm job %s by %ds (interactive in flight)", job_id, delay_seconds)
