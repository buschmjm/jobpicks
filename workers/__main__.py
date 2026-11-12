"""CLI for queue consumer and cron job entrypoints."""

from __future__ import annotations

import argparse
import logging
import sys

from workers import consumer
from workers.jobs import (
    daily_email,
    geocode_jobs,
    ingest,
    normalize_embed,
    queue_expiry,
    queue_topup,
    retention,
    score,
    source_health,
)

JOBS = {
    "ingest": ingest.main,
    "normalize-embed": normalize_embed.main,
    "score": score.main,
    "queue-topup": queue_topup.main,
    "daily-email": daily_email.main,
    "queue-expiry": queue_expiry.main,
    "source-health": source_health.main,
    "retention": retention.main,
    "geocode-jobs": geocode_jobs.main,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="workers", description="Job platform workers")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("consumer", help="Run the Postgres queue consumer")

    job_parser = sub.add_parser("job", help="Run a cron job entrypoint once")
    job_parser.add_argument(
        "name",
        choices=sorted(JOBS.keys()),
        help="Cron job name",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    args = build_parser().parse_args(argv)

    if args.command == "consumer":
        consumer.run_consumer(poll=True)
        return 0

    if args.command == "job":
        JOBS[args.name]()
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
