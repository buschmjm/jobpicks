"""Cron entrypoint: expire closed or stale unswiped queue cards."""

from __future__ import annotations

import logging

from core.database import SessionLocal
from core.queue_builder import QueueBuilder, SqlAlchemyQueueBuilderStore

logger = logging.getLogger(__name__)


def main() -> None:
    """Mark queued cards expired when jobs close or pass 28 days."""
    session = SessionLocal()
    try:
        builder = QueueBuilder(SqlAlchemyQueueBuilderStore(session))
        result = builder.expire_stale()
        session.commit()
        logger.info("queue expiry complete expired=%d", result.expired_count)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
