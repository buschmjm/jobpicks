#!/usr/bin/env python3
"""Probe JSearch / OpenWeb Ninja connectivity and report structured diagnostics."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

from ingest.adapters.jsearch import JSearchAdapter, _jsearch_base_url
from ingest.adapters.jsearch_errors import JSearchRequestError
from ingest.base import FetchParams
from ingest.quota import QuotaBudget, QuotaTracker


async def _probe(*, term: str, max_pages: int, max_days_old: int) -> dict:
    key = os.environ.get("JSEARCH_API_KEY", "")
    report: dict = {
        "api_key_set": bool(key.strip()),
        "api_key_length": len(key.strip()),
        "base_url": _jsearch_base_url(),
        "use_rapidapi": os.environ.get("JSEARCH_USE_RAPIDAPI", ""),
        "term": term,
        "max_pages": max_pages,
    }
    if not key.strip():
        report["status"] = "error"
        report["error"] = "JSEARCH_API_KEY not set"
        return report

    tracker = QuotaTracker()
    tracker.register(QuotaBudget(source="jsearch", daily_limit=1000))
    try:
        async with JSearchAdapter(quota=tracker, max_pages=max_pages) as adapter:
            result = await adapter.fetch(
                FetchParams(search_terms=(term,), max_days_old=max_days_old, results_per_page=10)
            )
        report["status"] = "ok"
        report["jobs_returned"] = len(result.jobs)
        report["filtered_out"] = result.filtered_out
        report["requests_used"] = result.requests_used
        if result.jobs:
            sample = result.jobs[0]
            report["sample"] = {
                "title": sample.title,
                "company": sample.company,
                "source_url": sample.source_url,
                "apply_url": sample.apply_url,
                "ats_type": sample.ats_type,
            }
        return report
    except JSearchRequestError as exc:
        report["status"] = "rate_limited" if exc.status_code == 429 else "http_error"
        report["http_status"] = exc.status_code
        report["error"] = str(exc)
        report["retry_after"] = exc.retry_after
        return report
    except Exception as exc:
        report["status"] = "error"
        report["error"] = f"{type(exc).__name__}: {exc}"
        return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--term", default="Technical Program Manager")
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--max-days-old", type=int, default=28)
    args = parser.parse_args()

    report = asyncio.run(
        _probe(term=args.term, max_pages=args.max_pages, max_days_old=args.max_days_old)
    )
    print(json.dumps(report, indent=2))
    if report.get("status") != "ok":
        sys.exit(1)


if __name__ == "__main__":
    main()
