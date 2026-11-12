"""Referral and email preference services (Workstream C)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from core.models import EventType, ReferralRedemption, User
from core.referrals import (
    REFERRAL_REWARD_DAYS,
    ensure_email_unsubscribe_token,
    ensure_referral_code,
    redeem_referral_code,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.email import SmtpConfig
from api.repositories.events_repo import log_event


class ReferralService:
    def status(self, session: Session, user_id: uuid.UUID) -> dict[str, object]:
        user = session.get(User, user_id)
        if user is None:
            raise LookupError("User not found")
        code = ensure_referral_code(session, user)
        redemptions = int(
            session.scalar(
                select(func.count())
                .select_from(ReferralRedemption)
                .where(ReferralRedemption.referrer_user_id == user_id)
            )
            or 0
        )
        config = SmtpConfig.from_env()
        share_url = f"{config.app_base_url}/auth?ref={code}"
        return {
            "referral_code": code,
            "share_url": share_url,
            "reward_days": REFERRAL_REWARD_DAYS,
            "successful_referrals": redemptions,
            "referred_by_applied": user.referred_by_user_id is not None,
        }

    def apply_code(self, session: Session, user_id: uuid.UUID, code: str) -> ReferralRedemption:
        user = session.get(User, user_id)
        if user is None:
            raise LookupError("User not found")
        redemption = redeem_referral_code(session, referee=user, code=code)
        log_event(
            session,
            event_type=EventType.REFERRAL_REDEEMED.value,
            user_id=user_id,
            entity_id=redemption.id,
            payload={
                "referrer_user_id": str(redemption.referrer_user_id),
                "reward_days": redemption.reward_days,
            },
        )
        return redemption


class EmailPreferencesService:
    def unsubscribe_url(self, user: User) -> str:
        token = ensure_email_unsubscribe_token(user)
        config = SmtpConfig.from_env()
        return f"{config.app_base_url}/api/email/unsubscribe/{token}"

    def unsubscribe_by_token(self, session: Session, token: str) -> User:
        user = session.scalar(select(User).where(User.email_unsubscribe_token == token))
        if user is None:
            raise LookupError("Invalid unsubscribe link")
        return self._unsubscribe_user(session, user, source="email_link")

    def unsubscribe(self, session: Session, user_id: uuid.UUID) -> User:
        user = session.get(User, user_id)
        if user is None:
            raise LookupError("User not found")
        return self._unsubscribe_user(session, user, source="settings")

    def _unsubscribe_user(self, session: Session, user: User, *, source: str) -> User:
        if user.unsubscribed_at is None:
            user.unsubscribed_at = datetime.now(tz=UTC)
            log_event(
                session,
                event_type=EventType.UNSUBSCRIBED.value,
                user_id=user.id,
                payload={"source": source},
            )
        return user

    def resubscribe(self, session: Session, user_id: uuid.UUID) -> None:
        user = session.get(User, user_id)
        if user is None:
            raise LookupError("User not found")
        was_unsubscribed = user.unsubscribed_at is not None
        user.unsubscribed_at = None
        ensure_email_unsubscribe_token(user)
        if was_unsubscribed:
            log_event(
                session,
                event_type=EventType.DIGEST_SUBSCRIBED.value,
                user_id=user.id,
                payload={"source": "settings"},
            )


referral_service = ReferralService()
email_preferences_service = EmailPreferencesService()
