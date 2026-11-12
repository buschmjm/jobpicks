"""Tests for USAJobs nightly sweep wiring."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from ingest.runner import build_usajobs_fetches
from ingest.sweep_config import USAJOBS_MAX_PAGES


def test_usajobs_skipped_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("USAJOBS_API_KEY", raising=False)
    assert build_usajobs_fetches(MagicMock()) == []


def test_usajobs_fetches_five_pages_when_keyed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USAJOBS_API_KEY", "test-key")
    monkeypatch.setenv("USAJOBS_USER_AGENT", "job-platform-test")
    pairs = build_usajobs_fetches(MagicMock())
    assert len(pairs) == USAJOBS_MAX_PAGES
    pages = [params.page for _, params in pairs]
    assert pages == [1, 2, 3, 4, 5]
    for _, params in pairs:
        assert params.search_terms == ()
        assert params.max_days_old == 1
