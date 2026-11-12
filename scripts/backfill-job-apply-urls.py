#!/usr/bin/env python3
"""Backfill jobs.apply_url, ats_type, and ats_metadata for existing rows."""

from __future__ import annotations

import argparse
import logging

from sqlalchemy import select

from core.apply.ats_detect import enrich_standard_job_apply
from core.apply.redirect_resolver import resolve_redirect_url
from core.database import SessionLocal
from core.models import Job

logger = logging.getLogger(__name__)


def backfill_apply_urls(
    *,
    limit: int | None = None,
    resolve_redirects: bool = False,
    dry_run: bool = False,
) -> dict[str, int]:
    stats = {"scanned": 0, "updated": 0, "skipped": 0}
    with SessionLocal() as session:
        query = select(Job).order_by(Job.updated_at.desc())
        if limit is not None:
            query = query.limit(limit)
        jobs = session.scalars(query).all()

        for job in jobs:
            stats["scanned"] += 1
            source_url = (job.source_url or "").strip()
            if not source_url:
                stats["skipped"] += 1
                continue

            candidate_apply = (job.apply_url or source_url).strip()
            if resolve_redirects:
                candidate_apply = resolve_redirect_url(candidate_apply)

            apply_url, ats_type, ats_metadata = enrich_standard_job_apply(
                source_url=source_url,
                apply_url=candidate_apply,
                ats_type=job.ats_type,
                ats_metadata=dict(job.ats_metadata or {}),
            )

            unchanged = (
                job.apply_url == apply_url
                and job.ats_type == ats_type
                and dict(job.ats_metadata or {}) == (ats_metadata or {})
            )
            if unchanged:
                stats["skipped"] += 1
                continue

            stats["updated"] += 1
            if dry_run:
                logger.info(
                    "would update job=%s apply_url=%s ats_type=%s",
                    job.id,
                    apply_url,
                    ats_type,
                )
                continue

            job.apply_url = apply_url
            job.ats_type = ats_type
            job.ats_metadata = ats_metadata or {}

        if not dry_run:
            session.commit()
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="Max jobs to scan")
    parser.add_argument(
        "--resolve-redirects",
        action="store_true",
        help="Follow one redirect hop before ATS detection",
    )
    parser.add_argument("--dry-run", action="store_true", help="Log changes without writing")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    stats = backfill_apply_urls(
        limit=args.limit,
        resolve_redirects=args.resolve_redirects,
        dry_run=args.dry_run,
    )
    print(stats)


if __name__ == "__main__":
    main()
