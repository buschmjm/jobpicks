"""Shared dependencies for App Store storefront gating."""

from __future__ import annotations

from typing import Annotated

from fastapi import Header


def app_client_kind(
    x_app_client: Annotated[str | None, Header(alias="X-App-Client")] = None,
) -> str | None:
    return x_app_client


def app_storefront(
    x_app_storefront: Annotated[str | None, Header(alias="X-App-Storefront")] = None,
) -> str | None:
    return x_app_storefront
