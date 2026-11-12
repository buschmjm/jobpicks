"""Persist and load ingest quota snapshots for admin dashboard."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from core.models import ScoringConfig
from sqlalchemy.orm import Session

from ingest.quota import QuotaTracker, default_quota_tracker

QUOTA_CONFIG_KEY = "ingest_quota"


def load_quota_tracker(session: Session) -> QuotaTracker:
    tracker = default_quota_tracker()
    row = session.get(ScoringConfig, QUOTA_CONFIG_KEY)
    if row is None:
        return tracker
    value: dict[str, Any] = row.value or {}
    stored_day = value.get("day")
    today = datetime.now(UTC).date().isoformat()
    if stored_day != today:
        return tracker
    for source, _budget in tracker.budgets.items():
        usage = int((value.get("sources") or {}).get(source, {}).get("used", 0))
        tracker._usage[source] = usage  # noqa: SLF001 — restore persisted day usage
        tracker._usage_day = date.fromisoformat(stored_day)
    return tracker


def save_quota_tracker(session: Session, tracker: QuotaTracker) -> None:
    sources: dict[str, dict[str, int]] = {}
    for source, budget in tracker.budgets.items():
        sources[source] = {"used": tracker.used(source), "limit": budget.daily_limit}
    payload = {
        "day": tracker._usage_day.isoformat(),  # noqa: SLF001
        "sources": sources,
    }
    row = session.get(ScoringConfig, QUOTA_CONFIG_KEY)
    if row is None:
        row = ScoringConfig(
            key=QUOTA_CONFIG_KEY,
            value=payload,
            description="Daily ingest API quota consumption",
        )
        session.add(row)
    else:
        row.value = payload
