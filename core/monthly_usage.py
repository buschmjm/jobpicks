"""Monthly tier-aware usage limits for Pro AI features."""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from core.entitlements import (
    PRO_ADVISOR_MESSAGES_PER_MONTH,
    PRO_PACKETS_PER_MONTH,
    PRO_RESUME_BUILDER_MESSAGES_PER_MONTH,
    is_pro_active,
)
from core.models import User

PRO_ADVISOR_MESSAGES_PER_DAY: int | None = None
PRO_RESUME_BUILDER_MESSAGES_PER_DAY: int | None = None


class MonthlyUsageFeature(enum.StrEnum):
    ADVISOR_MESSAGE = "advisor_message"
    RESUME_BUILDER_MESSAGE = "resume_builder_message"


class MonthlyLimitExceeded(Exception):
    def __init__(self, feature: MonthlyUsageFeature, used: int, limit: int) -> None:
        self.feature = feature
        self.used = used
        self.limit = limit
        feature_label = {
            MonthlyUsageFeature.ADVISOR_MESSAGE: "career advisor messages",
            MonthlyUsageFeature.RESUME_BUILDER_MESSAGE: "resume builder sessions",
            MonthlyUsageFeature.APPLICATION_PACKET: "AI application packets",
        }[feature]
        super().__init__(
            f"Pro plan includes {limit} {feature_label} per month. "
            f"You've used {used} this billing month."
        )


@dataclass(frozen=True)
class MonthlyUsageQuota:
    used: int
    limit: int | None
    unlimited: bool
    resets_at: datetime

    @property
    def remaining(self) -> int | None:
        if self.unlimited or self.limit is None:
            return None
        return max(0, self.limit - self.used)


def _usage_month_for_user(user: User, *, now: datetime | None = None) -> date:
    ref = now or datetime.now(tz=UTC)
    tz_name = (user.timezone or "UTC").strip() or "UTC"
    try:
        from zoneinfo import ZoneInfo

        local = ref.astimezone(ZoneInfo(tz_name))
    except Exception:
        local = ref.astimezone(UTC)
    return date(local.year, local.month, 1)


def _resets_at_for_user(user: User, *, now: datetime | None = None) -> datetime:
    ref = now or datetime.now(tz=UTC)
    tz_name = (user.timezone or "UTC").strip() or "UTC"
    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(tz_name)
        local = ref.astimezone(tz)
        if local.month == 12:
            next_month = date(local.year + 1, 1, 1)
        else:
            next_month = date(local.year, local.month + 1, 1)
        next_reset = datetime.combine(next_month, time.min, tzinfo=tz)
        return next_reset.astimezone(UTC)
    except Exception:
        if ref.month == 12:
            next_month = date(ref.year + 1, 1, 1)
        else:
            next_month = date(ref.year, ref.month + 1, 1)
        return datetime.combine(next_month, time.min, tzinfo=UTC)


def _monthly_limit_for_feature(user: User, feature: MonthlyUsageFeature) -> int | None:
    if not is_pro_active(user):
        return None
    if feature == MonthlyUsageFeature.ADVISOR_MESSAGE:
        return PRO_ADVISOR_MESSAGES_PER_MONTH
    if feature == MonthlyUsageFeature.RESUME_BUILDER_MESSAGE:
        return PRO_RESUME_BUILDER_MESSAGES_PER_MONTH
    raise ValueError(f"unknown feature: {feature}")


def monthly_feature_usage(
    session: Session,
    user: User,
    feature: MonthlyUsageFeature,
    *,
    now: datetime | None = None,
) -> int:
    from core.models import MonthlyUsageCounter

    usage_month = _usage_month_for_user(user, now=now)
    count = session.scalar(
        select(MonthlyUsageCounter.count)
        .where(
            MonthlyUsageCounter.user_id == user.id,
            MonthlyUsageCounter.feature == feature.value,
            MonthlyUsageCounter.usage_month == usage_month,
        )
        .limit(1)
    )
    return int(count or 0)


def monthly_usage_quota(
    session: Session,
    user: User,
    feature: MonthlyUsageFeature,
    *,
    now: datetime | None = None,
) -> MonthlyUsageQuota:
    used = monthly_feature_usage(session, user, feature, now=now)
    limit = _monthly_limit_for_feature(user, feature)
    return MonthlyUsageQuota(
        used=used,
        limit=limit,
        unlimited=limit is None,
        resets_at=_resets_at_for_user(user, now=now),
    )


def ensure_can_use_monthly_feature(session: Session, user: User, feature: MonthlyUsageFeature) -> None:
    quota = monthly_usage_quota(session, user, feature)
    if quota.unlimited or quota.limit is None:
        return
    if quota.used >= quota.limit:
        raise MonthlyLimitExceeded(feature, quota.used, quota.limit)


def increment_monthly_feature_usage(session: Session, user: User, feature: MonthlyUsageFeature) -> None:
    from core.models import MonthlyUsageCounter

    usage_month = _usage_month_for_user(user)
    stmt = (
        insert(MonthlyUsageCounter)
        .values(
            user_id=user.id,
            feature=feature.value,
            usage_month=usage_month,
            count=1,
        )
        .on_conflict_do_update(
            index_elements=["user_id", "feature", "usage_month"],
            set_={"count": MonthlyUsageCounter.count + 1},  # type: ignore[arg-type]
        )
    )
    session.execute(stmt)
    session.flush()
