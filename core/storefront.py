"""App Store storefront rules for external checkout (WS-8.6)."""

from __future__ import annotations

import os


def allowed_storefronts() -> set[str]:
    raw = os.environ.get("EXTERNAL_CHECKOUT_STOREFRONTS", "US").strip()
    if not raw:
        return set()
    return {part.strip().upper() for part in raw.split(",") if part.strip()}


def external_checkout_allowed(
    *,
    storefront: str | None,
    client_kind: str | None,
) -> bool:
    """
    Web: Stripe Checkout allowed in browser (any region).
    Mobile (Capacitor): only allowed for configured storefronts (default US only).
    """
    kind = (client_kind or "web").strip().lower()
    if kind != "mobile":
        return True
    if not storefront:
        return False
    return storefront.strip().upper() in allowed_storefronts()
