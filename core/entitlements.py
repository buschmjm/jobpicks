"""Plan tiers and feature entitlements (Workstream B1, plan E3.1)."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import UTC, datetime

from core.models import User

FREE_DAILY_TOPUP_CAP = 10
# Pro users see every ranked match available that day (no artificial daily cap).
PRO_DAILY_TOPUP_CAP: int | None = None
FREE_MAX_WHY_BULLETS = 1
PRO_MAX_WHY_BULLETS = 4
FREE_MAX_CAUTION_BULLETS = 0
PRO_MAX_CAUTION_BULLETS = 2

FREE_LIFETIME_PACKET_LIMIT = 2

PRO_MONTHLY_PRICE_CENTS = 1500
PRO_ADVISOR_MESSAGES_PER_MONTH = 80
PRO_RESUME_BUILDER_MESSAGES_PER_MONTH = 20
PRO_PACKETS_PER_MONTH = 20


class PlanTier(enum.StrEnum):
    FREE = "free"
    PRO = "pro"


class SubscriptionStatus(enum.StrEnum):
    NONE = "none"
    ACTIVE = "active"
    TRIALING = "trialing"
    PAST_DUE = "past_due"
    CANCELED = "canceled"


@dataclass(frozen=True)
class UserEntitlements:
    tier: PlanTier
    daily_topup_cap: int | None
    max_why_bullets: int
    max_caution_bullets: int
    show_score_breakdown: bool
    intraday_alerts: bool
    pro_monthly_price_cents: int | None = None
    subscription_period_end: datetime | None = None


def is_pro_active(user: User, *, now: datetime | None = None) -> bool:
    if user.plan_tier != PlanTier.PRO.value:
        return False
    status = user.subscription_status or SubscriptionStatus.NONE.value
    if status not in {SubscriptionStatus.ACTIVE.value, SubscriptionStatus.TRIALING.value}:
        return False
    if user.subscription_period_end is not None:
        ref = now or datetime.now(tz=UTC)
        end = user.subscription_period_end
        if end.tzinfo is None:
            end = end.replace(tzinfo=UTC)
        if end < ref:
            return False
    return True


def default_entitlements() -> UserEntitlements:
    return UserEntitlements(
        tier=PlanTier.FREE,
        daily_topup_cap=FREE_DAILY_TOPUP_CAP,
        max_why_bullets=FREE_MAX_WHY_BULLETS,
        max_caution_bullets=FREE_MAX_CAUTION_BULLETS,
        show_score_breakdown=False,
        intraday_alerts=False,
    )


def entitlements_for_user(user: User, *, now: datetime | None = None) -> UserEntitlements:
    if is_pro_active(user, now=now):
        return UserEntitlements(
            tier=PlanTier.PRO,
            daily_topup_cap=PRO_DAILY_TOPUP_CAP,
            max_why_bullets=PRO_MAX_WHY_BULLETS,
            max_caution_bullets=PRO_MAX_CAUTION_BULLETS,
            show_score_breakdown=True,
            intraday_alerts=True,
            pro_monthly_price_cents=PRO_MONTHLY_PRICE_CENTS,
            subscription_period_end=user.subscription_period_end,
        )
    return UserEntitlements(
        tier=PlanTier.FREE,
        daily_topup_cap=FREE_DAILY_TOPUP_CAP,
        max_why_bullets=FREE_MAX_WHY_BULLETS,
        max_caution_bullets=FREE_MAX_CAUTION_BULLETS,
        show_score_breakdown=False,
        intraday_alerts=False,
        pro_monthly_price_cents=PRO_MONTHLY_PRICE_CENTS,
        subscription_period_end=None,
    )


def apply_explanation_entitlements(
    explain: dict[str, object],
    components: dict[str, object],
    entitlements: UserEntitlements,
) -> tuple[list[str], list[str], dict[str, float] | None]:
    why_raw = explain.get("why_bullets")
    caution_raw = explain.get("caution_bullets")
    why = list(why_raw)[: entitlements.max_why_bullets] if isinstance(why_raw, list) else []
    caution = list(caution_raw)[: entitlements.max_caution_bullets] if isinstance(caution_raw, list) else []
    breakdown: dict[str, float] | None = None
    if entitlements.show_score_breakdown and components:
        breakdown = {
            key: float(value)
            for key, value in components.items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        }
    return why, caution, breakdown
