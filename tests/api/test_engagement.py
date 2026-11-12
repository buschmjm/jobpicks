"""Engagement API tests."""

from __future__ import annotations

from core.engagement import record_activity
from core.models import User, UserEngagement


def test_record_activity_increments_streak(db_session) -> None:
    user = User(email="engage@example.com")
    db_session.add(user)
    db_session.flush()

    record_activity(db_session, user.id, "session")
    row = db_session.get(UserEngagement, user.id)
    assert row is not None
    assert row.streak_days == 1
