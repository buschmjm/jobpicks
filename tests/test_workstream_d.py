"""Workstream D tests."""

from __future__ import annotations

from core.instrumentation import CLIENT_EVENT_TYPES


def test_client_event_types_include_deck_opened() -> None:
    assert "deck_opened" in CLIENT_EVENT_TYPES
