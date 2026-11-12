"""Pure functions for admin dashboard metrics (plan §11)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class EventRow:
    user_id: UUID | None
    type: str
    created_at: datetime
    payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class SourceHealthRow:
    source_name: str
    jobs_last_24h: int
    last_fetched_at: datetime | None
    status: str = "unknown"
    error: str | None = None


@dataclass(frozen=True)
class QuotaSnapshot:
    source: str
    used: int
    limit: int
    day: date


@dataclass
class DashboardMetrics:
    dau: int
    wau: int
    swipes_per_session: float
    right_swipe_rate: float
    queue_depth: int
    pro_users: int = 0
    free_users: int = 0
    referrals_total: int = 0
    digests_sent_24h: int = 0
    digest_open_rate_24h: float = 0.0
    llm_calls_24h: int = 0
    source_health: list[SourceHealthRow] = field(default_factory=list)
    quota: list[QuotaSnapshot] = field(default_factory=list)
    event_counts: dict[str, int] = field(default_factory=dict)


SWIPE_TYPES = frozenset({"swipe_right", "swipe_left", "skip"})
ACTIVE_TYPES = frozenset({"swipe_right", "swipe_left", "skip", "card_viewed", "login"})


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def count_active_users(events: list[EventRow], *, days: int, now: datetime | None = None) -> int:
    ref = _as_utc(now or datetime.now(UTC))
    cutoff = ref - timedelta(days=days)
    users: set[UUID] = set()
    for event in events:
        if event.user_id is None:
            continue
        if _as_utc(event.created_at) < cutoff:
            continue
        if event.type in ACTIVE_TYPES:
            users.add(event.user_id)
    return len(users)


def compute_swipes_per_session(events: list[EventRow], *, gap_minutes: int = 30) -> float:
    by_user: dict[UUID, list[datetime]] = defaultdict(list)
    for event in events:
        if event.user_id is None or event.type not in SWIPE_TYPES:
            continue
        by_user[event.user_id].append(_as_utc(event.created_at))

    session_counts: list[float] = []
    gap = timedelta(minutes=gap_minutes)
    for timestamps in by_user.values():
        timestamps.sort()
        if not timestamps:
            continue
        per_session: list[int] = []
        current = 1
        prev = timestamps[0]
        for ts in timestamps[1:]:
            if ts - prev > gap:
                per_session.append(current)
                current = 1
            else:
                current += 1
            prev = ts
        per_session.append(current)
        session_counts.append(sum(per_session) / len(per_session))
    if not session_counts:
        return 0.0
    return round(sum(session_counts) / len(session_counts), 2)


def compute_right_swipe_rate(events: list[EventRow]) -> float:
    right = 0
    total = 0
    for event in events:
        if event.type == "swipe_right":
            right += 1
            total += 1
        elif event.type in {"swipe_left", "skip"}:
            total += 1
    if total == 0:
        return 0.0
    return round(right / total, 4)


def aggregate_event_counts(events: list[EventRow]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for event in events:
        counts[event.type] += 1
    return dict(counts)


def build_dashboard_metrics(
    *,
    events: list[EventRow],
    queue_depth: int,
    source_health: list[SourceHealthRow],
    quota: list[QuotaSnapshot],
    now: datetime | None = None,
    pro_users: int = 0,
    free_users: int = 0,
    referrals_total: int = 0,
    digests_sent_24h: int = 0,
    digest_open_rate_24h: float = 0.0,
    llm_calls_24h: int = 0,
) -> DashboardMetrics:
    return DashboardMetrics(
        dau=count_active_users(events, days=1, now=now),
        wau=count_active_users(events, days=7, now=now),
        swipes_per_session=compute_swipes_per_session(events),
        right_swipe_rate=compute_right_swipe_rate(events),
        queue_depth=queue_depth,
        pro_users=pro_users,
        free_users=free_users,
        referrals_total=referrals_total,
        digests_sent_24h=digests_sent_24h,
        digest_open_rate_24h=digest_open_rate_24h,
        llm_calls_24h=llm_calls_24h,
        source_health=source_health,
        quota=quota,
        event_counts=aggregate_event_counts(events),
    )


def source_health_from_fetches(
    rows: list[tuple[str, datetime]],
    *,
    now: datetime | None = None,
) -> list[SourceHealthRow]:
    """Aggregate job_sources rows as (source_name, fetched_at)."""
    ref = _as_utc(now or datetime.now(UTC))
    cutoff = ref - timedelta(hours=24)
    counts: dict[str, int] = defaultdict(int)
    last_seen: dict[str, datetime] = {}
    for source_name, fetched_at in rows:
        ts = _as_utc(fetched_at)
        if ts >= cutoff:
            counts[source_name] += 1
        if source_name not in last_seen or ts > last_seen[source_name]:
            last_seen[source_name] = ts

    sources = sorted(set(counts) | set(last_seen))
    result: list[SourceHealthRow] = []
    for source in sources:
        last = last_seen.get(source)
        status = "healthy"
        if last is None:
            status = "unknown"
        elif ref - last > timedelta(hours=6):
            status = "stale"
        result.append(
            SourceHealthRow(
                source_name=source,
                jobs_last_24h=counts.get(source, 0),
                last_fetched_at=last,
                status=status,
            )
        )
    return result
