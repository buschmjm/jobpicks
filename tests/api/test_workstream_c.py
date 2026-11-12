"""Workstream C API integration tests."""

from __future__ import annotations

from datetime import UTC, datetime

from api.services.revenue_service import email_preferences_service, referral_service
from core.models import EventType, Profile, User
from core.referrals import (
    REFERRAL_REWARD_DAYS,
    ensure_email_unsubscribe_token,
    ensure_referral_code,
    redeem_referral_code,
)
from sqlalchemy import select
from sqlalchemy.orm import Session


def test_referral_code_unique(db_session: Session) -> None:
    user = User(email="referrer@example.com")
    db_session.add(user)
    db_session.flush()
    code = ensure_referral_code(db_session, user)
    assert len(code) == 8
    assert ensure_referral_code(db_session, user) == code


def test_redeem_grants_both_users_pro(db_session: Session) -> None:
    referrer = User(email="referrer@example.com")
    referee = User(email="referee@example.com")
    db_session.add_all([referrer, referee])
    db_session.flush()
    code = ensure_referral_code(db_session, referrer)
    redemption = redeem_referral_code(db_session, referee=referee, code=code)
    assert redemption.reward_days == REFERRAL_REWARD_DAYS
    assert referee.plan_tier == "pro"
    assert referrer.plan_tier == "pro"
    assert referee.referred_by_user_id == referrer.id


def test_email_unsubscribe_sets_timestamp(db_session: Session) -> None:
    user = User(email="unsub@example.com")
    db_session.add(user)
    db_session.flush()
    ensure_email_unsubscribe_token(user)
    db_session.flush()
    token = user.email_unsubscribe_token
    assert token is not None

    updated = email_preferences_service.unsubscribe_by_token(db_session, token)
    assert updated.unsubscribed_at is not None


def test_referral_status_returns_share_url(db_session: Session) -> None:
    user = User(email="share@example.com")
    db_session.add(user)
    db_session.flush()
    data = referral_service.status(db_session, user.id)
    assert data["referral_code"]
    assert "ref=" in str(data["share_url"])


def test_digest_skips_unonboarded_users(db_session: Session) -> None:
    from workers.jobs.daily_email import _eligible_users

    user = User(email="new@example.com", is_active=True)
    db_session.add(user)
    db_session.flush()
    assert _eligible_users(db_session) == []

    profile = Profile(user_id=user.id, parsed_resume={})
    profile.onboarding_completed_at = datetime.now(tz=UTC)
    db_session.add(profile)
    db_session.commit()
    emails = [row.email for row in _eligible_users(db_session)]
    assert "new@example.com" in emails


def test_unsubscribe_logs_event(db_session: Session) -> None:
    from core.models import Event

    user = User(email="event@example.com")
    db_session.add(user)
    db_session.flush()
    ensure_email_unsubscribe_token(user)
    db_session.flush()
    email_preferences_service.unsubscribe_by_token(db_session, user.email_unsubscribe_token or "")
    db_session.commit()
    events = db_session.scalars(select(Event).where(Event.user_id == user.id)).all()
    assert any(event.type == EventType.UNSUBSCRIBED.value for event in events)


def test_settings_unsubscribe_and_resubscribe(db_session: Session) -> None:
    from core.models import Event

    user = User(email="settings-unsub@example.com")
    db_session.add(user)
    db_session.flush()

    email_preferences_service.unsubscribe(db_session, user.id)
    db_session.commit()
    db_session.refresh(user)
    assert user.unsubscribed_at is not None

    events = db_session.scalars(select(Event).where(Event.user_id == user.id)).all()
    assert any(
        event.type == EventType.UNSUBSCRIBED.value
        and (event.payload or {}).get("source") == "settings"
        for event in events
    )

    email_preferences_service.resubscribe(db_session, user.id)
    db_session.commit()
    db_session.refresh(user)
    assert user.unsubscribed_at is None

    events = db_session.scalars(select(Event).where(Event.user_id == user.id)).all()
    assert any(event.type == EventType.DIGEST_SUBSCRIBED.value for event in events)
