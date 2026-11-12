"""Public app URL roots for OAuth redirects and billing links."""

from __future__ import annotations

import os
from urllib.parse import urlparse

from fastapi import Request

from api.mount import normalize_mount_path


def app_mount_path() -> str:
    return normalize_mount_path(os.environ.get("APP_MOUNT_PATH"))


def configured_app_bases() -> frozenset[str]:
    bases: set[str] = set()
    primary = os.environ.get("APP_BASE_URL", "https://jobs.jbuschmann.com").strip().rstrip("/")
    if primary:
        bases.add(primary)
    extra = os.environ.get("APP_ALT_BASE_URLS", "")
    for part in extra.split(","):
        cleaned = part.strip().rstrip("/")
        if cleaned:
            bases.add(cleaned)
    return frozenset(bases)


def public_app_root(base: str) -> str:
    """Return canonical browser root (origin + optional mount path)."""
    root = base.strip().rstrip("/")
    mount = app_mount_path()
    if mount and not root.endswith(mount):
        root = f"{root}{mount}"
    return root


def public_app_roots() -> frozenset[str]:
    return frozenset(public_app_root(base) for base in configured_app_bases())


def allowed_redirect_uris() -> frozenset[str]:
    return frozenset(f"{root}/auth/callback" for root in public_app_roots())


def public_app_base_from_request(request: Request) -> str:
    """Return the public app root matching the incoming request host when possible."""
    host = (request.headers.get("host") or "").split(":")[0].lower()
    forwarded = request.headers.get("x-forwarded-proto")
    scheme = (forwarded.split(",")[0].strip() if forwarded else request.url.scheme) or "https"

    for root in public_app_roots():
        parsed = urlparse(root if "://" in root else f"https://{root}")
        if parsed.hostname and parsed.hostname.lower() == host:
            return root

    mount = app_mount_path()
    origin = f"{scheme}://{host}"
    return f"{origin}{mount}" if mount else origin
