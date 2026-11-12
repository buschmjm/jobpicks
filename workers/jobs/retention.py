"""Cron entrypoint: data retention — resume purge, event anonymization, old job purge."""

from __future__ import annotations

import logging

from api.services.privacy_service import anonymize_old_events, purge_stale_resume_files
from core.database import SessionLocal
from core.job_retention import purge_closed_api_jobs

logger = logging.getLogger(__name__)


def main() -> None:
    """Purge resume files >90 days, anonymize events, delete closed API jobs >30 days posted."""
    session = SessionLocal()
    try:
        resume_removed = purge_stale_resume_files(session)
        events_anonymized = anonymize_old_events(session)
        jobs_purged = purge_closed_api_jobs(session)
        session.commit()
        logger.info(
            "retention complete resume_files_removed=%d events_anonymized=%d jobs_purged=%d",
            resume_removed,
            events_anonymized,
            jobs_purged,
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
