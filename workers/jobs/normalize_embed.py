"""Cron entrypoint: normalize non-JSearch jobs and embed (E2.5 batch)."""

from __future__ import annotations

import logging
import os

from core.batch_jobs import embed_jobs_batch, normalize_jobs_batch
from core.database import SessionLocal

from workers.consumer import enqueue_job

logger = logging.getLogger(__name__)


def main() -> None:
    """Run LLM normalization + embedding batches, then enqueue scoring."""
    normalize_batch = int(os.environ.get("NORMALIZE_BATCH_SIZE", "50"))
    embed_batch = int(os.environ.get("EMBED_BATCH_SIZE", "200"))
    max_normalize_rounds = int(os.environ.get("NORMALIZE_MAX_ROUNDS", "10"))

    session = SessionLocal()
    try:
        norm_totals = {"normalized": 0, "heuristic": 0, "errors": 0, "skipped": 0}
        for round_num in range(max_normalize_rounds):
            stats = normalize_jobs_batch(session, batch_size=normalize_batch)
            for key in norm_totals:
                norm_totals[key] += stats.get(key, 0)
            processed = stats.get("normalized", 0) + stats.get("heuristic", 0)
            if processed == 0:
                break
            logger.info("normalize round %d stats=%s", round_num + 1, stats)

        embed_stats = embed_jobs_batch(session, batch_size=embed_batch)
        enqueue_job(session, "cron_score", {})
        session.commit()
        logger.info(
            "normalize_embed complete normalize=%s embed=%s → cron_score",
            norm_totals,
            embed_stats,
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
