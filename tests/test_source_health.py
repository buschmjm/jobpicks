"""Tests for source health JSearch gating."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from workers.jobs import source_health


@pytest.mark.asyncio
async def test_check_all_adapters_skips_jsearch_unless_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JSEARCH_API_KEY", "test-key")
    monkeypatch.delenv("JSEARCH_ENABLED", raising=False)
    monkeypatch.delenv("ADZUNA_APP_ID", raising=False)
    monkeypatch.delenv("ADZUNA_APP_KEY", raising=False)
    monkeypatch.delenv("USAJOBS_API_KEY", raising=False)

    with patch("workers.jobs.source_health.JSearchAdapter") as jsearch_cls:
        with patch("workers.jobs.source_health._probe_adapter", return_value={"status": "healthy"}):
            results = await source_health.check_all_adapters()
    jsearch_cls.assert_not_called()
    assert "jsearch" not in results
    assert "remotive" in results


@pytest.mark.asyncio
async def test_check_all_adapters_includes_usajobs_when_keyed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USAJOBS_API_KEY", "test-key")
    monkeypatch.setenv("USAJOBS_USER_AGENT", "test@example.com")
    monkeypatch.delenv("ADZUNA_APP_ID", raising=False)
    monkeypatch.delenv("ADZUNA_APP_KEY", raising=False)
    monkeypatch.delenv("JSEARCH_ENABLED", raising=False)

    with patch("workers.jobs.source_health.USAJobsAdapter") as usajobs_cls:
        usajobs_cls.return_value.source_name = "usajobs"
        with patch("workers.jobs.source_health._probe_adapter", return_value={"status": "healthy"}):
            results = await source_health.check_all_adapters()
    usajobs_cls.assert_called_once()
    assert "usajobs" in results
