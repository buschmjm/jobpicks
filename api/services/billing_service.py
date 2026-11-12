"""Stripe Checkout, portal, and webhook handling (Workstream B2)."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from core.entitlements import PRO_MONTHLY_PRICE_CENTS, PlanTier, SubscriptionStatus
from core.models import User
from sqlalchemy.orm import Session

from api.settings import settings

logger = logging.getLogger(__name__)


class BillingNotConfiguredError(RuntimeError):
    pass


def _stripe_enabled() -> bool:
    return bool(settings.stripe_secret_key)


def _stripe_client() -> Any:
    if not _stripe_enabled():
        raise BillingNotConfiguredError("Stripe is not configured")
    import stripe

    stripe.api_key = settings.stripe_secret_key
    return stripe


def _price_id_for_pro() -> str:
    price_id = settings.stripe_price_id_monthly_1500
    if not price_id:
        raise BillingNotConfiguredError("No Stripe price configured for Pro ($15/mo)")
    return price_id


def ensure_pro_price(user: User) -> int:
    user.price_variant_cents = PRO_MONTHLY_PRICE_CENTS
    return PRO_MONTHLY_PRICE_CENTS


def create_checkout_session(session: Session, user: User) -> str:
    stripe = _stripe_client()
    price_cents = ensure_pro_price(user)
    price_id = _price_id_for_pro()
    if user.stripe_customer_id is None:
        customer = stripe.Customer.create(email=user.email, metadata={"user_id": str(user.id)})
        user.stripe_customer_id = customer["id"]
        session.flush()

    checkout = stripe.checkout.Session.create(
        mode="subscription",
        customer=user.stripe_customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{settings.app_base_url}/settings?billing=success",
        cancel_url=f"{settings.app_base_url}/settings?billing=canceled",
        client_reference_id=str(user.id),
        metadata={"user_id": str(user.id), "price_cents": str(price_cents)},
        subscription_data={"metadata": {"user_id": str(user.id)}},
    )
    url = checkout.get("url")
    if not url:
        raise RuntimeError("Stripe checkout session missing url")
    return str(url)


def create_portal_session(user: User) -> str:
    stripe = _stripe_client()
    if not user.stripe_customer_id:
        raise LookupError("No Stripe customer for user")
    portal = stripe.billing_portal.Session.create(
        customer=user.stripe_customer_id,
        return_url=f"{settings.app_base_url}/settings",
    )
    url = portal.get("url")
    if not url:
        raise RuntimeError("Stripe portal session missing url")
    return str(url)


def cancel_subscription_at_period_end(session: Session, user: User) -> datetime | None:
    """Cancel Stripe subscription at period end, or end referral-only Pro immediately."""
    from core.models import EventType

    from api.repositories.events_repo import log_event

    if user.stripe_subscription_id:
        stripe = _stripe_client()
        subscription = stripe.Subscription.modify(
            user.stripe_subscription_id,
            cancel_at_period_end=True,
        )
        apply_subscription_to_user(user, dict(subscription))
        log_event(
            session,
            event_type=EventType.SUBSCRIPTION_CANCELED.value,
            user_id=user.id,
            payload={"cancel_at_period_end": True, "source": "api"},
        )
        return user.subscription_period_end

    if user.plan_tier == PlanTier.PRO.value:
        user.subscription_status = SubscriptionStatus.CANCELED.value
        user.plan_tier = PlanTier.FREE.value
        log_event(
            session,
            event_type=EventType.SUBSCRIPTION_CANCELED.value,
            user_id=user.id,
            payload={"cancel_at_period_end": False, "source": "referral_credit"},
        )
    return user.subscription_period_end


def _period_end_from_subscription(subscription: dict[str, Any]) -> datetime | None:
    raw = subscription.get("current_period_end")
    if raw is None:
        return None
    return datetime.fromtimestamp(int(raw), tz=UTC)


def apply_subscription_to_user(user: User, subscription: dict[str, Any]) -> None:
    status = str(subscription.get("status") or SubscriptionStatus.NONE.value)
    user.stripe_subscription_id = str(subscription.get("id") or user.stripe_subscription_id or "")
    user.subscription_status = status
    user.subscription_period_end = _period_end_from_subscription(subscription)
    if status in {SubscriptionStatus.ACTIVE.value, SubscriptionStatus.TRIALING.value}:
        user.plan_tier = PlanTier.PRO.value
        user.price_variant_cents = PRO_MONTHLY_PRICE_CENTS
    elif status in {SubscriptionStatus.CANCELED.value, SubscriptionStatus.PAST_DUE.value}:
        user.plan_tier = PlanTier.FREE.value


def handle_checkout_completed(session: Session, checkout: dict[str, Any]) -> None:
    user_id_raw = checkout.get("client_reference_id") or (checkout.get("metadata") or {}).get("user_id")
    if not user_id_raw:
        logger.warning("checkout.session.completed missing user_id")
        return
    user = session.get(User, uuid.UUID(str(user_id_raw)))
    if user is None:
        logger.warning("checkout.session.completed user not found: %s", user_id_raw)
        return
    customer_id = checkout.get("customer")
    if customer_id:
        user.stripe_customer_id = str(customer_id)
    subscription_id = checkout.get("subscription")
    if not subscription_id:
        return
    stripe = _stripe_client()
    subscription = stripe.Subscription.retrieve(str(subscription_id))
    apply_subscription_to_user(user, dict(subscription))


def handle_subscription_event(session: Session, subscription: dict[str, Any]) -> None:
    metadata = subscription.get("metadata") or {}
    user_id_raw = metadata.get("user_id")
    user: User | None = None
    if user_id_raw:
        user = session.get(User, uuid.UUID(str(user_id_raw)))
    if user is None:
        sub_id = subscription.get("id")
        if sub_id:
            from sqlalchemy import select

            user = session.scalar(select(User).where(User.stripe_subscription_id == str(sub_id)))
    if user is None:
        customer_id = subscription.get("customer")
        if customer_id:
            from sqlalchemy import select

            user = session.scalar(select(User).where(User.stripe_customer_id == str(customer_id)))
    if user is None:
        logger.warning("subscription event could not resolve user")
        return
    apply_subscription_to_user(user, subscription)


def handle_webhook_payload(session: Session, payload: bytes, signature: str | None) -> None:
    stripe = _stripe_client()
    if not settings.stripe_webhook_secret:
        raise BillingNotConfiguredError("STRIPE_WEBHOOK_SECRET not configured")
    if not signature:
        raise ValueError("Missing Stripe-Signature header")
    event = stripe.Webhook.construct_event(payload, signature, settings.stripe_webhook_secret)
    event_type = event.get("type")
    data_object = (event.get("data") or {}).get("object") or {}

    if event_type == "checkout.session.completed":
        handle_checkout_completed(session, dict(data_object))
    elif event_type in {
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "customer.subscription.created",
    }:
        handle_subscription_event(session, dict(data_object))
        if event_type == "customer.subscription.deleted":
            from core.models import EventType

            from api.repositories.events_repo import log_event

            user_id_raw = (data_object.get("metadata") or {}).get("user_id")
            if user_id_raw:
                log_event(
                    session,
                    event_type=EventType.SUBSCRIPTION_CANCELED.value,
                    user_id=uuid.UUID(str(user_id_raw)),
                    payload={"source": "stripe_webhook"},
                )
    else:
        logger.debug("ignored stripe event type=%s", event_type)
