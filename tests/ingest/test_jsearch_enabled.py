"""Tests for JSEARCH_ENABLED gating."""

from __future__ import annotations

import pytest
from ingest.sweep_config import jsearch_enabled


def test_jsearch_enabled_false_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JSEARCH_ENABLED", raising=False)
    assert jsearch_enabled() is False


def test_jsearch_enabled_true_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JSEARCH_ENABLED", "true")
    assert jsearch_enabled() is True
