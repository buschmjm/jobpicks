"""Auth router — Keycloak OIDC (production) with legacy cookie logout for dev/tests."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlparse

import httpx
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status

from api.auth import revoke_session, session_cookie_settings
from api.deps import get_current_user
from api.app_urls import allowed_redirect_uris as _allowed_redirect_uris
from api.app_urls import public_app_base_from_request
from api.app_urls import public_app_roots
from api.keycloak_auth import auth_backend, get_keycloak_settings
from api.schemas import AuthConfigResponse, SessionUser

router = APIRouter(prefix="/auth", tags=["auth"])

_ALLOWED_GRANTS = frozenset({"authorization_code", "refresh_token"})


def _primary_app_root() -> str:
    roots = sorted(public_app_roots())
    if not roots:
        return "https://jobs.jbuschmann.com"
    return roots[0]


def _proxied_token_endpoint(request: Request | None = None) -> str:
    root = public_app_base_from_request(request) if request is not None else _primary_app_root()
    return f"{root}/api/auth/oidc/token"


@router.get("/config", response_model=AuthConfigResponse)
async def auth_config(request: Request) -> AuthConfigResponse:
    settings = get_keycloak_settings()
    if settings is None or auth_backend() != "keycloak":
        return AuthConfigResponse(mode="legacy")
    return AuthConfigResponse(
        mode="keycloak",
        authority=settings.issuer,
        client_id=settings.client_id,
        token_endpoint=_proxied_token_endpoint(request),
    )


@router.post("/oidc/token")
async def oidc_token_proxy(request: Request) -> Response:
    """Exchange auth codes server-side (browser calls to Keycloak token URL are blocked by Cloudflare)."""
    settings = get_keycloak_settings()
    if settings is None or auth_backend() != "keycloak":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OIDC not configured")

    body = await request.body()
    form = dict(parse_qsl(body.decode(), keep_blank_values=True))

    client_id = form.get("client_id", "")
    if client_id != settings.client_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid client_id")

    grant_type = form.get("grant_type", "")
    if grant_type not in _ALLOWED_GRANTS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported grant_type")

    if grant_type == "authorization_code":
        redirect_uri = form.get("redirect_uri", "")
        if redirect_uri not in _allowed_redirect_uris():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid redirect_uri")

    # The browser session was issued at KEYCLOAK_URL (https). This proxy calls
    # Keycloak in-cluster over http, so without forwarded proto/host Keycloak
    # treats the issuer as http:// and rejects the refresh token.
    public = urlparse(settings.url)
    forwarded_port = "443" if public.scheme == "https" else str(public.port or 80)
    async with httpx.AsyncClient(timeout=15.0) as client:
        upstream = await client.post(
            settings.token_uri,
            content=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Forwarded-Proto": public.scheme or "https",
                "X-Forwarded-Host": public.netloc,
                "X-Forwarded-Port": forwarded_port,
            },
        )

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type", "application/json"),
    )


@router.get("/me", response_model=SessionUser)
async def get_me(user: SessionUser = Depends(get_current_user)) -> SessionUser:
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    session: str | None = Cookie(default=None),
) -> None:
    """Clear legacy session cookie if present (Keycloak sign-out is SPA-driven)."""
    if session:
        revoke_session(session)
    cookie = session_cookie_settings()
    response.delete_cookie(key=cookie["key"], path=cookie["path"])
