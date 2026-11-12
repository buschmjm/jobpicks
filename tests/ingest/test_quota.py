"""Tests for per-source quota tracking."""

import pytest
from ingest.quota import QuotaBudget, QuotaExceededError, QuotaTracker, default_quota_tracker


def test_consume_and_remaining() -> None:
    tracker = QuotaTracker()
    tracker.register(QuotaBudget(source="jsearch", daily_limit=5))

    for _ in range(5):
        tracker.consume("jsearch")

    assert tracker.remaining("jsearch") == 0
    with pytest.raises(QuotaExceededError):
        tracker.consume("jsearch")


def test_try_consume_returns_false_when_exhausted() -> None:
    tracker = QuotaTracker()
    tracker.register(QuotaBudget(source="jsearch", daily_limit=1))
    assert tracker.try_consume("jsearch") is True
    assert tracker.try_consume("jsearch") is False


def test_default_tracker_has_all_sources() -> None:
    tracker = default_quota_tracker()
    assert tracker.remaining("jsearch") > 0
    assert tracker.remaining("adzuna") > 0
    assert tracker.remaining("remotive") > 0


def test_warning_threshold() -> None:
    tracker = QuotaTracker()
    tracker.register(QuotaBudget(source="jsearch", daily_limit=10, warn_threshold_pct=0.8))
    for _ in range(8):
        tracker.consume("jsearch")
    assert tracker.is_warning("jsearch") is True
