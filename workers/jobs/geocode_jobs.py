"""Cron entrypoint: geocode open jobs missing coordinates."""

from __future__ import annotations

import logging

from core.database import SessionLocal
from core.geo.geocode import resolve_job_coordinates
from core.models import Job, JobStatus
from sqlalchemy import or_, select

logger = logging.getLogger(__name__)

_BATCH_LIMIT = 200


def main() -> None:
    session = SessionLocal()
    try:
        rows = session.scalars(
            select(Job)
            .where(Job.status == JobStatus.OPEN.value)
            .where(or_(Job.latitude.is_(None), Job.longitude.is_(None)))
            .limit(_BATCH_LIMIT)
        ).all()
        resolved = 0
        for job in rows:
            if resolve_job_coordinates(session, job) is not None:
                resolved += 1
        session.commit()
        logger.info("geocode jobs complete scanned=%d resolved=%d", len(rows), resolved)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
