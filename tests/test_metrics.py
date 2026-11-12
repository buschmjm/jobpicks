"""Tests for admin dashboard metric pure functions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from core.metrics import (
    EventRow,
    QuotaSnapshot,
    SourceHealthRow,
    build_dashboard_metrics,
    compute_right_swipe_rate,
    compute_swipes_per_session,
    count_active_users,
    source_health_from_fetches,
)

USER_A = UUID("00000000-0000-0000-0000-000000000001")
USER_B = UUID("00000000-0000-0000-0000-000000000002")
NOW = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)


def _event(user_id: UUID | None, type_: str, minutes_ago: int) -> EventRow:
    return EventRow(
        user_id=user_id,
        type=type_,
        created_at=NOW - timedelta(minutes=minutes_ago),
    )


def test_count_active_users_dau_wau() -> None:
    events = [
        _event(USER_A, "login", 60),
        _event(USER_B, "swipe_right", 120),
        _event(USER_B, "swipe_left", 60 * 24 * 3),
    ]
    assert count_active_users(events, days=1, now=NOW) == 2
    assert count_active_users(events, days=7, now=NOW) == 2


def test_right_swipe_rate() -> None:
    events = [
        _event(USER_A, "swipe_right", 1),
        _event(USER_A, "swipe_right", 2),
        _event(USER_A, "swipe_left", 3),
        _event(USER_A, "skip", 4),
    ]
    assert compute_right_swipe_rate(events) == 0.5


def test_swipes_per_session_groups_by_gap() -> None:
    events = [
        _event(USER_A, "swipe_right", 10),
        _event(USER_A, "swipe_left", 9),
        _event(USER_A, "swipe_right", 60),  # new session (>30 min gap)
    ]
    assert compute_swipes_per_session(events, gap_minutes=30) == 1.5


def test_source_health_from_fetches() -> None:
    now = NOW
    rows = [
        ("jsearch", now - timedelta(hours=1)),
        ("jsearch", now - timedelta(hours=2)),
        ("adzuna", now - timedelta(hours=10)),
    ]
    health = source_health_from_fetches(rows, now=now)
    by_source = {row.source_name: row for row in health}
    assert by_source["jsearch"].jobs_last_24h == 2
    assert by_source["jsearch"].status == "healthy"
    assert by_source["adzuna"].status == "stale"


def test_build_dashboard_metrics() -> None:
    events = [
        _event(USER_A, "swipe_right", 5),
        _event(USER_A, "swipe_left", 4),
        _event(USER_B, "login", 3),
    ]
    metrics = build_dashboard_metrics(
        events=events,
        queue_depth=42,
        source_health=[
            SourceHealthRow("jsearch", 10, NOW - timedelta(hours=1), "healthy"),
        ],
        quota=[QuotaSnapshot("jsearch", 40, 100, NOW.date())],
        now=NOW,
    )
    assert metrics.queue_depth == 42
    assert metrics.dau == 2
    assert metrics.quota[0].used == 40
    assert metrics.source_health[0].source_name == "jsearch"
