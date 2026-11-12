"""Cron entrypoint: nightly ingest pipeline."""

from __future__ import annotations

import logging

from core.database import SessionLocal
from core.deck_bootstrap import fan_out_pending_backfills
from ingest.runner import run_ingest

from workers.consumer import enqueue_job

logger = logging.getLogger(__name__)


def main() -> None:
    """Run the ingest pipeline across configured source adapters."""
    session = SessionLocal()
    try:
        stats = run_ingest(session)
        enqueue_job(session, "cron_normalize_embed", {})
        backfill_count = fan_out_pending_backfills(session, enqueue=enqueue_job)
        session.commit()
        logger.info(
            "ingest complete stats=%s enqueued=cron_normalize_embed backfills=%d",
            stats,
            backfill_count,
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
