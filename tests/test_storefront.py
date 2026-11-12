"""Storefront / region-gated external checkout (WS-8.6)."""

from __future__ import annotations

import pytest
from core.storefront import external_checkout_allowed


def test_external_checkout_web_always_allowed() -> None:
    assert external_checkout_allowed(storefront="US", client_kind="web") is True
    assert external_checkout_allowed(storefront="GB", client_kind="web") is True
    assert external_checkout_allowed(storefront="GB", client_kind=None) is True


def test_external_checkout_mobile_us_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXTERNAL_CHECKOUT_STOREFRONTS", "US")
    assert external_checkout_allowed(storefront="US", client_kind="mobile") is True
    assert external_checkout_allowed(storefront="GB", client_kind="mobile") is False
    assert external_checkout_allowed(storefront="CA", client_kind="mobile") is False


def test_external_checkout_mobile_missing_storefront(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXTERNAL_CHECKOUT_STOREFRONTS", "US")
    assert external_checkout_allowed(storefront=None, client_kind="mobile") is False


def test_external_checkout_mobile_multi_region(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXTERNAL_CHECKOUT_STOREFRONTS", "US,CA,GB")
    assert external_checkout_allowed(storefront="CA", client_kind="mobile") is True
    assert external_checkout_allowed(storefront="AU", client_kind="mobile") is False
