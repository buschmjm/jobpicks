"""Daily and monthly tier-aware usage limits for AI features and deck matches."""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from core.entitlements import (
    FREE_DAILY_TOPUP_CAP,
    FREE_LIFETIME_PACKET_LIMIT,
    PRO_ADVISOR_MESSAGES_PER_MONTH,
    PRO_PACKETS_PER_MONTH,
    PRO_RESUME_BUILDER_MESSAGES_PER_MONTH,
    entitlements_for_user,
    is_pro_active,
)
from core.models import User, UserJobQueue
from core.monthly_usage import (
    MonthlyLimitExceeded,
    MonthlyUsageFeature,
    ensure_can_use_monthly_feature,
    increment_monthly_feature_usage,
    monthly_usage_quota,
)
from core.packet_entitlements import lifetime_packets_used, packets_used_this_month

FREE_ADVISOR_MESSAGES_PER_DAY = 5
FREE_RESUME_BUILDER_MESSAGES_PER_DAY = 3


class UsageFeature(enum.StrEnum):
    ADVISOR_MESSAGE = "advisor_message"
    RESUME_BUILDER_MESSAGE = "resume_builder_message"


class DailyLimitExceeded(Exception):
    def __init__(self, feature: UsageFeature, used: int, limit: int) -> None:
        self.feature = feature
        self.used = used
        self.limit = limit
        feature_label = {
            UsageFeature.ADVISOR_MESSAGE: "career advisor messages",
            UsageFeature.RESUME_BUILDER_MESSAGE: "resume builder messages",
        }[feature]
        super().__init__(
            f"Free plan includes {limit} {feature_label} per day. "
            f"You've used {used} today. Upgrade to Pro for a higher monthly allowance."
        )


@dataclass(frozen=True)
class UsageQuota:
    used: int
    limit: int | None
    unlimited: bool
    resets_at: datetime
    monthly: bool = False
    lifetime: bool = False

    @property
    def remaining(self) -> int | None:
        if self.unlimited or self.limit is None:
            return None
        return max(0, self.limit - self.used)


def _usage_date_for_user(user: User, *, now: datetime | None = None) -> date:
    ref = now or datetime.now(tz=UTC)
    tz_name = (user.timezone or "UTC").strip() or "UTC"
    try:
        from zoneinfo import ZoneInfo

        local = ref.astimezone(ZoneInfo(tz_name))
    except Exception:
        local = ref.astimezone(UTC)
    return local.date()


def _resets_at_for_user(user: User, *, now: datetime | None = None) -> datetime:
    ref = now or datetime.now(tz=UTC)
    tz_name = (user.timezone or "UTC").strip() or "UTC"
    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(tz_name)
        local = ref.astimezone(tz)
        next_midnight = datetime.combine(local.date() + timedelta(days=1), time.min, tzinfo=tz)
        return next_midnight.astimezone(UTC)
    except Exception:
        tomorrow = ref.date() + timedelta(days=1)
        return datetime.combine(tomorrow, time.min, tzinfo=UTC)


def _daily_limit_for_feature(user: User, feature: UsageFeature) -> int | None:
    if is_pro_active(user):
        return None
    if feature == UsageFeature.ADVISOR_MESSAGE:
        return FREE_ADVISOR_MESSAGES_PER_DAY
    if feature == UsageFeature.RESUME_BUILDER_MESSAGE:
        return FREE_RESUME_BUILDER_MESSAGES_PER_DAY
    raise ValueError(f"unknown feature: {feature}")


def _monthly_feature_for_usage(feature: UsageFeature) -> MonthlyUsageFeature:
    if feature == UsageFeature.ADVISOR_MESSAGE:
        return MonthlyUsageFeature.ADVISOR_MESSAGE
    if feature == UsageFeature.RESUME_BUILDER_MESSAGE:
        return MonthlyUsageFeature.RESUME_BUILDER_MESSAGE
    raise ValueError(f"unknown feature: {feature}")


def daily_feature_usage(
    session: Session,
    user: User,
    feature: UsageFeature,
    *,
    now: datetime | None = None,
) -> int:
    from core.models import DailyUsageCounter

    usage_date = _usage_date_for_user(user, now=now)
    count = session.scalar(
        select(DailyUsageCounter.count)
        .where(
            DailyUsageCounter.user_id == user.id,
            DailyUsageCounter.feature == feature.value,
            DailyUsageCounter.usage_date == usage_date,
        )
        .limit(1)
    )
    return int(count or 0)


def deck_matches_added_today(session: Session, user_id: uuid.UUID, *, now: datetime | None = None) -> int:
    ref = now or datetime.now(tz=UTC)
    start = datetime.combine(ref.date(), time.min, tzinfo=UTC)
    count = session.scalar(
        select(func.count())
        .select_from(UserJobQueue)
        .where(
            UserJobQueue.user_id == user_id,
            UserJobQueue.created_at >= start,
        )
    )
    return int(count or 0)


def usage_quota(
    session: Session,
    user: User,
    feature: UsageFeature,
    *,
    now: datetime | None = None,
) -> UsageQuota:
    if is_pro_active(user):
        monthly = monthly_usage_quota(session, user, _monthly_feature_for_usage(feature), now=now)
        return UsageQuota(
            used=monthly.used,
            limit=monthly.limit,
            unlimited=monthly.unlimited,
            resets_at=monthly.resets_at,
            monthly=True,
        )
    used = daily_feature_usage(session, user, feature, now=now)
    limit = _daily_limit_for_feature(user, feature)
    return UsageQuota(
        used=used,
        limit=limit,
        unlimited=limit is None,
        resets_at=_resets_at_for_user(user, now=now),
        monthly=False,
    )


def deck_matches_quota(session: Session, user: User, *, now: datetime | None = None) -> UsageQuota:
    ent = entitlements_for_user(user, now=now)
    used = deck_matches_added_today(session, user.id, now=now)
    unlimited = ent.daily_topup_cap is None
    return UsageQuota(
        used=used,
        limit=ent.daily_topup_cap,
        unlimited=unlimited,
        resets_at=_resets_at_for_user(user, now=now),
    )


def ensure_can_use_feature(session: Session, user: User, feature: UsageFeature) -> None:
    if is_pro_active(user):
        ensure_can_use_monthly_feature(session, user, _monthly_feature_for_usage(feature))
        return
    quota = usage_quota(session, user, feature)
    if quota.unlimited or quota.limit is None:
        return
    if quota.used >= quota.limit:
        raise DailyLimitExceeded(feature, quota.used, quota.limit)


def increment_feature_usage(session: Session, user: User, feature: UsageFeature) -> None:
    if is_pro_active(user):
        increment_monthly_feature_usage(session, user, _monthly_feature_for_usage(feature))
        return
    from core.models import DailyUsageCounter

    usage_date = _usage_date_for_user(user)
    stmt = (
        insert(DailyUsageCounter)
        .values(
            user_id=user.id,
            feature=feature.value,
            usage_date=usage_date,
            count=1,
        )
        .on_conflict_do_update(
            index_elements=["user_id", "feature", "usage_date"],
            set_={"count": DailyUsageCounter.count + 1},  # type: ignore[arg-type]
        )
    )
    session.execute(stmt)
    session.flush()


def packet_usage_quota(session: Session, user: User, *, now: datetime | None = None) -> UsageQuota:
    from core.monthly_usage import _resets_at_for_user as monthly_resets_at

    if is_pro_active(user):
        used = packets_used_this_month(session, user.id, now=now)
        return UsageQuota(
            used=used,
            limit=PRO_PACKETS_PER_MONTH,
            unlimited=False,
            resets_at=monthly_resets_at(user, now=now),
            monthly=True,
        )
    used = lifetime_packets_used(session, user.id)
    return UsageQuota(
        used=used,
        limit=FREE_LIFETIME_PACKET_LIMIT,
        unlimited=False,
        resets_at=_resets_at_for_user(user, now=now),
        lifetime=True,
    )


def usage_summary_for_user(session: Session, user: User) -> dict[str, object]:
    advisor = usage_quota(session, user, UsageFeature.ADVISOR_MESSAGE)
    builder = usage_quota(session, user, UsageFeature.RESUME_BUILDER_MESSAGE)
    deck = deck_matches_quota(session, user)
    packets = packet_usage_quota(session, user)
    ent = entitlements_for_user(user)

    def _serialize(quota: UsageQuota) -> dict[str, object]:
        return {
            "used": quota.used,
            "limit": quota.limit,
            "remaining": quota.remaining,
            "unlimited": quota.unlimited,
            "resets_at": quota.resets_at.isoformat(),
            "monthly": quota.monthly,
            "lifetime": quota.lifetime,
        }

    return {
        "tier": ent.tier.value,
        "deck_matches": _serialize(deck),
        "advisor_messages": _serialize(advisor),
        "resume_builder_messages": _serialize(builder),
        "packets": _serialize(packets),
        "pro_monthly_price_cents": ent.pro_monthly_price_cents,
        "pro_advisor_messages_per_month": PRO_ADVISOR_MESSAGES_PER_MONTH,
        "pro_resume_builder_messages_per_month": PRO_RESUME_BUILDER_MESSAGES_PER_MONTH,
        "pro_packets_per_month": PRO_PACKETS_PER_MONTH,
    }


__all__ = [
    "DailyLimitExceeded",
    "MonthlyLimitExceeded",
    "UsageFeature",
    "UsageQuota",
    "deck_matches_quota",
    "ensure_can_use_feature",
    "increment_feature_usage",
    "usage_quota",
    "usage_summary_for_user",
]
