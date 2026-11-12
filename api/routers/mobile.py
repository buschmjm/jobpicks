"""Mobile launch readiness (WS-8) — public, unauthenticated."""

from __future__ import annotations

from core.storefront import allowed_storefronts
from fastapi import APIRouter

from api.routers.well_known import mobile_link_config
from api.schemas import MobileReadinessResponse

router = APIRouter(prefix="/mobile", tags=["mobile"])


@router.get("/readiness", response_model=MobileReadinessResponse)
def mobile_readiness() -> MobileReadinessResponse:
    """Deploy smoke test for Universal/App Links + storefront billing gate."""
    link = mobile_link_config()
    storefronts = sorted(allowed_storefronts())
    return MobileReadinessResponse(
        apple_universal_links_configured=link["apple_universal_links_configured"],
        android_app_links_configured=link["android_app_links_configured"],
        apple_bundle_id=link["apple_bundle_id"],
        android_package=link["android_package"],
        auth_callback_paths=link["auth_callback_paths"],
        external_checkout_storefronts=storefronts,
    )
