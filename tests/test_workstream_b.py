"""Workstream B acceptance tests (BT1–BT4)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from core.entitlements import (
    FREE_DAILY_TOPUP_CAP,
    PRO_DAILY_TOPUP_CAP,
    PRO_MONTHLY_PRICE_CENTS,
    PlanTier,
    SubscriptionStatus,
    apply_explanation_entitlements,
    default_entitlements,
    entitlements_for_user,
    is_pro_active,
)
from core.models import User


def _user(**kwargs: object) -> User:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "email": "test@example.com",
        "plan_tier": PlanTier.FREE.value,
        "subscription_status": None,
        "subscription_period_end": None,
        "price_variant_cents": None,
    }
    defaults.update(kwargs)
    return User(**defaults)  # type: ignore[arg-type]


class TestBT1EntitlementTiers:
    def test_free_defaults(self) -> None:
        ent = entitlements_for_user(_user())
        assert ent.tier == PlanTier.FREE
        assert ent.daily_topup_cap == FREE_DAILY_TOPUP_CAP
        assert ent.max_why_bullets == 1
        assert ent.show_score_breakdown is False
        assert ent.pro_monthly_price_cents == PRO_MONTHLY_PRICE_CENTS

    def test_pro_active_entitlements(self) -> None:
        user = _user(
            plan_tier=PlanTier.PRO.value,
            subscription_status=SubscriptionStatus.ACTIVE.value,
            subscription_period_end=datetime.now(tz=UTC) + timedelta(days=20),
        )
        ent = entitlements_for_user(user)
        assert ent.tier == PlanTier.PRO
        assert ent.daily_topup_cap == PRO_DAILY_TOPUP_CAP
        assert ent.max_why_bullets == 4
        assert ent.show_score_breakdown is True


class TestBT2ProExpiry:
    def test_expired_subscription_is_not_pro(self) -> None:
        user = _user(
            plan_tier=PlanTier.PRO.value,
            subscription_status=SubscriptionStatus.ACTIVE.value,
            subscription_period_end=datetime.now(tz=UTC) - timedelta(days=1),
        )
        assert is_pro_active(user) is False
        assert entitlements_for_user(user).tier == PlanTier.FREE


class TestBT4ExplanationGating:
    def test_free_user_gets_truncated_explanations(self) -> None:
        explain = {
            "why_bullets": ["a", "b", "c", "d"],
            "caution_bullets": ["x", "y"],
        }
        components = {"semantic": 0.8, "skills": 0.7}
        why, caution, breakdown = apply_explanation_entitlements(
            explain,
            components,
            default_entitlements(),
        )
        assert why == ["a"]
        assert caution == []
        assert breakdown is None

    def test_pro_user_gets_full_breakdown(self) -> None:
        user = _user(
            plan_tier=PlanTier.PRO.value,
            subscription_status=SubscriptionStatus.ACTIVE.value,
            subscription_period_end=datetime.now(tz=UTC) + timedelta(days=5),
        )
        ent = entitlements_for_user(user)
        why, caution, breakdown = apply_explanation_entitlements(
            {"why_bullets": ["a", "b"], "caution_bullets": ["c"]},
            {"semantic": 0.5, "match_score": 0.6},
            ent,
        )
        assert why == ["a", "b"]
        assert caution == ["c"]
        assert breakdown == {"semantic": 0.5, "match_score": 0.6}
