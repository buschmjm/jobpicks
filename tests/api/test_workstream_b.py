"""Workstream B API tests (billing status + topup cap)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from api.services.billing_service import apply_subscription_to_user, ensure_pro_price
from core.entitlements import (
    PRO_MONTHLY_PRICE_CENTS,
    PlanTier,
    SubscriptionStatus,
    entitlements_for_user,
)
from core.models import User
from core.queue_builder import QueueBuilder, SqlAlchemyQueueBuilderStore
from sqlalchemy.orm import Session


def test_free_user_entitlements_from_db(db_session: Session) -> None:
    user = User(email="billing@example.com")
    db_session.add(user)
    db_session.commit()

    ensure_pro_price(user)
    ent = entitlements_for_user(user)
    assert ent.tier == PlanTier.FREE
    assert ent.daily_topup_cap == 10
    assert ent.max_why_bullets == 1
    assert user.price_variant_cents == PRO_MONTHLY_PRICE_CENTS


def test_pro_user_daily_topup_cap(db_session: Session) -> None:
    user = User(
        email="pro@example.com",
        plan_tier=PlanTier.PRO.value,
        subscription_status=SubscriptionStatus.ACTIVE.value,
        subscription_period_end=datetime.now(tz=UTC) + timedelta(days=10),
    )
    db_session.add(user)
    db_session.commit()

    store = SqlAlchemyQueueBuilderStore(db_session)
    assert store.load_daily_topup_cap(user.id) == 10_000


def test_apply_subscription_promotes_user(db_session: Session) -> None:
    user = User(email="stripe@example.com")
    db_session.add(user)
    db_session.flush()

    apply_subscription_to_user(
        user,
        {
            "id": "sub_123",
            "status": "active",
            "current_period_end": int((datetime.now(tz=UTC) + timedelta(days=30)).timestamp()),
        },
    )
    assert user.plan_tier == PlanTier.PRO.value
    assert user.subscription_status == SubscriptionStatus.ACTIVE.value
    assert user.price_variant_cents == PRO_MONTHLY_PRICE_CENTS


def test_queue_builder_store_default_cap(db_session: Session) -> None:
    user_id = uuid.uuid4()
    store = SqlAlchemyQueueBuilderStore(db_session)
    from core.entitlements import FREE_DAILY_TOPUP_CAP

    assert store.load_daily_topup_cap(user_id) == FREE_DAILY_TOPUP_CAP
    builder = QueueBuilder(store)
    assert builder is not None
