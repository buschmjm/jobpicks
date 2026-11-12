"""Cron entrypoint: nightly queue top-up (≤30/day cap from scoring_config)."""

from __future__ import annotations

import logging

from core.database import SessionLocal
from core.models import User
from core.queue_builder import QueueBuilder, SqlAlchemyQueueBuilderStore
from sqlalchemy import select

logger = logging.getLogger(__name__)


def main() -> None:
    """Append today's matching jobs to each active user's queue."""
    session = SessionLocal()
    try:
        store = SqlAlchemyQueueBuilderStore(session)
        builder = QueueBuilder(store)
        users = session.scalars(select(User.id).where(User.is_active.is_(True))).all()
        total = 0
        for user_id in users:
            result = builder.topup_user(user_id)
            total += len(result.enqueued)
            if result.enqueued:
                user = session.get(User, user_id)
                if user is not None:
                    from workers.jobs.intraday_alert import send_intraday_alert

                    try:
                        send_intraday_alert(session, user, new_jobs_count=len(result.enqueued))
                    except Exception:
                        logger.exception("intraday alert failed user=%s", user_id)
            logger.info(
                "topup user=%s enqueued=%d capped=%d",
                result.user_id,
                len(result.enqueued),
                result.capped_count,
            )
        session.commit()
        logger.info("queue top-up complete users=%d jobs=%d", len(users), total)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
