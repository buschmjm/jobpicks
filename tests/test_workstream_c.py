"""Workstream C acceptance tests (CT1–CT5)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from core.digest_schedule import is_digest_send_window
from core.entitlements import PlanTier, SubscriptionStatus
from core.models import User
from core.referrals import (
    ensure_email_unsubscribe_token,
    grant_pro_credit,
)


def _user(email: str) -> User:
    return User(id=uuid.uuid4(), email=email)


class TestCT3UnsubscribeToken:
    def test_unsubscribe_token_generated(self) -> None:
        user = _user("u@example.com")
        token = ensure_email_unsubscribe_token(user)
        assert len(token) >= 16
        assert ensure_email_unsubscribe_token(user) == token


class TestCT4DigestWindow:
    def test_chicago_six_am_window(self) -> None:
        now = datetime(2026, 9, 2, 11, 30, tzinfo=UTC)  # 6:30 AM Chicago (CDT)
        assert is_digest_send_window(timezone="America/Chicago", now=now) is True

    def test_outside_window_skips(self) -> None:
        now = datetime(2026, 9, 2, 15, 30, tzinfo=UTC)  # 10:30 AM Chicago
        assert is_digest_send_window(timezone="America/Chicago", now=now) is False


class TestCT5ProCredit:
    def test_grant_extends_existing_period(self) -> None:
        user = _user("pro@example.com")
        user.subscription_period_end = datetime.now(tz=UTC) + timedelta(days=10)
        before = user.subscription_period_end
        end = grant_pro_credit(user, days=30)
        assert end > before
        assert user.subscription_status == SubscriptionStatus.ACTIVE.value
        assert user.plan_tier == PlanTier.PRO.value
