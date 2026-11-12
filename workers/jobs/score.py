"""Cron entrypoint: verify batch pipeline health and enqueue queue top-up."""

from __future__ import annotations

import logging

from core.database import SessionLocal
from core.models import Job, JobStatus, Profile
from sqlalchemy import func, select

from workers.consumer import enqueue_job

logger = logging.getLogger(__name__)


def main() -> None:
    """
    Scoring runs at queue-build time (SqlAlchemyQueueBuilderStore).
    This step logs corpus health and chains to nightly top-up.
    """
    session = SessionLocal()
    try:
        open_jobs = session.scalar(
            select(func.count()).select_from(Job).where(Job.status == JobStatus.OPEN.value)
        )
        missing_embed = session.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.status == JobStatus.OPEN.value)
            .where(Job.embedding.is_(None))
        )
        onboarded = session.scalar(
            select(func.count())
            .select_from(Profile)
            .where(Profile.onboarding_completed_at.is_not(None))
        )
        logger.info(
            "score health open_jobs=%s missing_embeddings=%s onboarded_users=%s",
            open_jobs,
            missing_embed,
            onboarded,
        )
        enqueue_job(session, "cron_queue_topup", {})
        session.commit()
        logger.info("score enqueued next step=cron_queue_topup")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
