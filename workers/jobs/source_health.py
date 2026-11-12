"""Cron entrypoint: source adapter health checks (E2.12)."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime
from typing import Any

from core.database import SessionLocal
from core.models import ScoringConfig
from ingest.adapters.adzuna import AdzunaAdapter
from ingest.adapters.jsearch import JSearchAdapter
from ingest.adapters.remotive import RemotiveAdapter
from ingest.adapters.usajobs import USAJobsAdapter
from ingest.base import FetchParams, SourceAdapter
from ingest.quota import QuotaTracker, default_quota_tracker
from ingest.quota_store import load_quota_tracker, save_quota_tracker
from ingest.sweep_config import jsearch_enabled
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

SOURCE_HEALTH_KEY = "source_health"


def _health_config_value(checks: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {"checked_at": datetime.now(UTC).isoformat(), "sources": checks}


async def _probe_adapter(adapter: SourceAdapter) -> dict[str, Any]:
    try:
        result = await adapter.fetch(
            FetchParams(search_terms=("devops",), results_per_page=1, page=1, max_days_old=7)
        )
        return {
            "status": "healthy",
            "jobs_returned": len(result.jobs),
            "requests_used": result.requests_used,
            "error": None,
            "http_status": None,
        }
    except Exception as exc:
        http_status = getattr(exc, "status_code", None)
        return {
            "status": "unhealthy",
            "jobs_returned": 0,
            "requests_used": 0,
            "error": str(exc)[:500],
            "http_status": http_status,
        }


def _build_probe_adapters(quota: QuotaTracker) -> list[SourceAdapter]:
    adapters: list[SourceAdapter] = []
    if os.environ.get("ADZUNA_APP_ID") and os.environ.get("ADZUNA_APP_KEY"):
        try:
            adapters.append(AdzunaAdapter(quota=quota))
        except ValueError:
            logger.warning("skipping adzuna health probe: credentials invalid")
    if jsearch_enabled() and os.environ.get("JSEARCH_API_KEY"):
        adapters.append(JSearchAdapter(quota=quota))
    if os.environ.get("USAJOBS_API_KEY"):
        try:
            adapters.append(USAJobsAdapter(quota=quota))
        except ValueError:
            logger.warning("skipping usajobs health probe: credentials invalid")
    adapters.append(RemotiveAdapter(quota=quota))
    return adapters


async def check_all_adapters() -> dict[str, dict[str, Any]]:
    quota = default_quota_tracker()
    results: dict[str, dict[str, Any]] = {}
    for adapter in _build_probe_adapters(quota):
        async with adapter:
            results[adapter.source_name] = await _probe_adapter(adapter)
    return results


def persist_health(session: Session, checks: dict[str, dict[str, Any]]) -> None:
    payload = _health_config_value(checks)
    row = session.get(ScoringConfig, SOURCE_HEALTH_KEY)
    if row is None:
        row = ScoringConfig(
            key=SOURCE_HEALTH_KEY,
            value=payload,
            description="Latest source adapter health probe results",
        )
        session.add(row)
    else:
        row.value = payload


def run_source_health(session: Session | None = None) -> dict[str, dict[str, Any]]:
    owns_session = session is None
    db = session or SessionLocal()
    try:
        if os.environ.get("SOURCE_HEALTH_SKIP_PROBE", "").lower() in {"1", "true", "yes"}:
            checks = {
                name: {"status": "skipped", "jobs_returned": 0, "requests_used": 0, "error": None}
                for name in ("adzuna", "jsearch", "usajobs", "remotive")
            }
        else:
            checks = asyncio.run(check_all_adapters())
        persist_health(db, checks)
        tracker = load_quota_tracker(db)
        save_quota_tracker(db, tracker)
        db.commit()
        logger.info("source_health complete: %s", checks)
        return checks
    finally:
        if owns_session:
            db.close()


def main() -> None:
    run_source_health()
