"""Revenue prerequisites: referrals and email tokens (Workstream C)."""

from __future__ import annotations

import secrets
import string
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.entitlements import PlanTier, SubscriptionStatus
from core.models import ReferralRedemption, User

REFERRAL_REWARD_DAYS = 90
REFERRAL_CODE_ALPHABET = string.ascii_uppercase + string.digits
REFERRAL_CODE_LENGTH = 8


def generate_referral_code() -> str:
    return "".join(secrets.choice(REFERRAL_CODE_ALPHABET) for _ in range(REFERRAL_CODE_LENGTH))


def ensure_referral_code(session: Session, user: User) -> str:
    if user.referral_code:
        return user.referral_code
    for _ in range(12):
        candidate = generate_referral_code()
        exists = session.scalar(select(User.id).where(User.referral_code == candidate).limit(1))
        if exists is None:
            user.referral_code = candidate
            session.flush()
            return candidate
    raise RuntimeError("Failed to allocate unique referral code")


def ensure_email_unsubscribe_token(user: User) -> str:
    if user.email_unsubscribe_token:
        return user.email_unsubscribe_token
    user.email_unsubscribe_token = secrets.token_urlsafe(24)
    return user.email_unsubscribe_token


def grant_pro_credit(user: User, *, days: int, now: datetime | None = None) -> datetime:
    """Extend or start Pro access (referral reward or promo credit)."""
    ref = now or datetime.now(tz=UTC)
    base = user.subscription_period_end
    if base is None or base < ref:
        base = ref
    if base.tzinfo is None:
        base = base.replace(tzinfo=UTC)
    end = base + timedelta(days=days)
    user.plan_tier = PlanTier.PRO.value
    user.subscription_status = SubscriptionStatus.ACTIVE.value
    user.subscription_period_end = end
    return end


def redeem_referral_code(
    session: Session,
    *,
    referee: User,
    code: str,
    now: datetime | None = None,
) -> ReferralRedemption:
    normalized = code.strip().upper()
    if not normalized:
        raise ValueError("Referral code is required")
    if referee.referred_by_user_id is not None:
        raise ValueError("Referral code already applied")

    existing = session.scalar(
        select(ReferralRedemption.id).where(ReferralRedemption.referee_user_id == referee.id).limit(1)
    )
    if existing is not None:
        raise ValueError("Referral already redeemed")

    referrer = session.scalar(select(User).where(User.referral_code == normalized))
    if referrer is None:
        raise LookupError("Invalid referral code")
    if referrer.id == referee.id:
        raise ValueError("Cannot use your own referral code")

    ref_now = now or datetime.now(tz=UTC)
    referee.referred_by_user_id = referrer.id
    grant_pro_credit(referee, days=REFERRAL_REWARD_DAYS, now=ref_now)
    grant_pro_credit(referrer, days=REFERRAL_REWARD_DAYS, now=ref_now)

    redemption = ReferralRedemption(
        referrer_user_id=referrer.id,
        referee_user_id=referee.id,
        reward_days=REFERRAL_REWARD_DAYS,
        redeemed_at=ref_now,
    )
    session.add(redemption)
    session.flush()
    return redemption
