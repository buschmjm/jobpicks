"""Billing and subscription API (Workstream B3)."""

from __future__ import annotations

from core.daily_usage import usage_summary_for_user
from core.entitlements import entitlements_for_user
from core.packet_entitlements import lifetime_packet_limit_for_user, lifetime_packets_used
from core.storefront import external_checkout_allowed
from fastapi import APIRouter, Depends, HTTPException, Request, status

from api.deps import DbSession, get_current_user
from api.deps_storefront import app_client_kind, app_storefront
from api.repositories.user_repo import UserRepository
from api.schemas import (
    BillingCancelResponse,
    BillingCheckoutResponse,
    BillingPortalResponse,
    BillingStatusResponse,
    UsageQuotaResponse,
    UsageSummaryResponse,
)
from api.services.billing_service import (
    BillingNotConfiguredError,
    cancel_subscription_at_period_end,
    create_checkout_session,
    create_portal_session,
    ensure_pro_price,
    handle_webhook_payload,
)

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/status", response_model=BillingStatusResponse)
def billing_status(
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
    client_kind: str | None = Depends(app_client_kind),
    storefront: str | None = Depends(app_storefront),
) -> BillingStatusResponse:
    row = UserRepository(db).get_by_id(user.id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    ensure_pro_price(row)
    db.flush()
    ent = entitlements_for_user(row)
    packets_used = lifetime_packets_used(db, row.id)
    packets_limit = lifetime_packet_limit_for_user(row)
    checkout_allowed = external_checkout_allowed(storefront=storefront, client_kind=client_kind)
    usage_raw = usage_summary_for_user(db, row)

    def _quota(data: dict[str, object]) -> UsageQuotaResponse:
        return UsageQuotaResponse(
            used=int(data["used"]),
            limit=data.get("limit") if data.get("limit") is not None else None,
            remaining=data.get("remaining") if data.get("remaining") is not None else None,
            unlimited=bool(data.get("unlimited")),
            resets_at=str(data["resets_at"]) if data.get("resets_at") else None,
            lifetime=bool(data.get("lifetime")),
            monthly=bool(data.get("monthly")),
        )

    usage = UsageSummaryResponse(
        tier=usage_raw["tier"],  # type: ignore[arg-type]
        deck_matches=_quota(usage_raw["deck_matches"]),  # type: ignore[arg-type]
        advisor_messages=_quota(usage_raw["advisor_messages"]),  # type: ignore[arg-type]
        resume_builder_messages=_quota(usage_raw["resume_builder_messages"]),  # type: ignore[arg-type]
        packets=_quota(usage_raw["packets"]),  # type: ignore[arg-type]
    )
    return BillingStatusResponse(
        tier=ent.tier.value,
        daily_topup_cap=ent.daily_topup_cap,
        max_why_bullets=ent.max_why_bullets,
        show_score_breakdown=ent.show_score_breakdown,
        intraday_alerts=ent.intraday_alerts,
        pro_monthly_price_cents=ent.pro_monthly_price_cents,
        price_variant_cents=ent.pro_monthly_price_cents,
        subscription_status=row.subscription_status,
        subscription_period_end=row.subscription_period_end,
        stripe_configured=_stripe_configured(),
        lifetime_packets_used=packets_used,
        lifetime_packets_limit=packets_limit,
        external_checkout_allowed=checkout_allowed,
        usage=usage,
    )


@router.post("/checkout", response_model=BillingCheckoutResponse)
def start_checkout(
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
    client_kind: str | None = Depends(app_client_kind),
    storefront: str | None = Depends(app_storefront),
) -> BillingCheckoutResponse:
    if not external_checkout_allowed(storefront=storefront, client_kind=client_kind):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "In-app upgrades are only available in supported App Store regions. "
                "Subscribe on the web — your Pro plan works in the app."
            ),
        )
    row = UserRepository(db).get_by_id(user.id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    try:
        url = create_checkout_session(db, row)
    except BillingNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    db.commit()
    return BillingCheckoutResponse(checkout_url=url)


@router.post("/portal", response_model=BillingPortalResponse)
def customer_portal(
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> BillingPortalResponse:
    row = UserRepository(db).get_by_id(user.id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    try:
        url = create_portal_session(row)
    except BillingNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return BillingPortalResponse(portal_url=url)


@router.post("/cancel", response_model=BillingCancelResponse)
def cancel_subscription(
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> BillingCancelResponse:
    row = UserRepository(db).get_by_id(user.id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    try:
        period_end = cancel_subscription_at_period_end(db, row)
    except BillingNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    db.commit()
    return BillingCancelResponse(
        canceled=True,
        cancel_at_period_end=bool(row.stripe_subscription_id),
        subscription_period_end=period_end,
    )


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def stripe_webhook(request: Request, db: DbSession) -> dict[str, str]:
    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    try:
        handle_webhook_payload(db, payload, signature)
    except BillingNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    return {"status": "ok"}


def _stripe_configured() -> bool:
    from api.settings import settings

    return bool(settings.stripe_secret_key and settings.stripe_webhook_secret)
