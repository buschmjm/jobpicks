"""Well-known routes for mobile deep linking (Capacitor / Universal Links)."""

from __future__ import annotations

import json
import os
from typing import TypedDict

from api.mount import join_mount_path, mount_path_from_env
from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response

router = APIRouter(tags=["well-known"])

_APPLE_TEAM_ID = os.environ.get("APPLE_TEAM_ID", "").strip()
_APPLE_BUNDLE_ID = os.environ.get(
    "APPLE_BUNDLE_ID",
    os.environ.get("ANDROID_PACKAGE", "com.jbuschmann.jobpicks"),
).strip()
_ANDROID_PACKAGE = os.environ.get("ANDROID_PACKAGE", "com.jbuschmann.jobpicks").strip()
_ANDROID_SHA256 = os.environ.get("ANDROID_SHA256_CERT_FINGERPRINT", "").strip()
_AUTH_CALLBACK_PATHS = (
    join_mount_path(mount_path_from_env(), "/auth/callback"),
    join_mount_path(mount_path_from_env(), "/auth/callback/*"),
)


class MobileLinkConfig(TypedDict):
    apple_universal_links_configured: bool
    android_app_links_configured: bool
    apple_team_id_set: bool
    apple_bundle_id: str | None
    android_package: str | None
    auth_callback_paths: list[str]


def mobile_link_config() -> MobileLinkConfig:
    apple_ready = bool(_APPLE_TEAM_ID and _APPLE_BUNDLE_ID)
    android_ready = bool(_ANDROID_PACKAGE and _ANDROID_SHA256)
    return {
        "apple_universal_links_configured": apple_ready,
        "android_app_links_configured": android_ready,
        "apple_team_id_set": bool(_APPLE_TEAM_ID),
        "apple_bundle_id": _APPLE_BUNDLE_ID or None,
        "android_package": _ANDROID_PACKAGE or None,
        "auth_callback_paths": list(_AUTH_CALLBACK_PATHS),
    }


@router.get("/.well-known/apple-app-site-association")
async def apple_app_site_association() -> Response:
    """Universal Links — requires APPLE_TEAM_ID + APPLE_BUNDLE_ID before App Store."""
    details: list[dict[str, object]] = []
    if _APPLE_TEAM_ID and _APPLE_BUNDLE_ID:
        details.append(
            {
                "appID": f"{_APPLE_TEAM_ID}.{_APPLE_BUNDLE_ID}",
                "paths": list(_AUTH_CALLBACK_PATHS),
            }
        )
    payload = {"applinks": {"apps": [], "details": details}}
    return Response(
        content=json.dumps(payload),
        media_type="application/json",
        headers={"Cache-Control": "public, max-age=300"},
    )


@router.get("/.well-known/assetlinks.json")
async def android_asset_links() -> JSONResponse:
    """Android App Links — set ANDROID_SHA256_CERT_FINGERPRINT before Play submission."""
    statements: list[dict[str, object]] = []
    if _ANDROID_SHA256:
        statements.append(
            {
                "relation": ["delegate_permission/common.handle_all_urls"],
                "target": {
                    "namespace": "android_app",
                    "package_name": _ANDROID_PACKAGE,
                    "sha256_cert_fingerprints": [_ANDROID_SHA256],
                },
            }
        )
    return JSONResponse(
        content=statements,
        headers={"Cache-Control": "public, max-age=300"},
    )
