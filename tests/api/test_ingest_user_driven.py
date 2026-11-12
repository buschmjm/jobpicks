"""Tests for ingest runner with user-driven search terms and nightly sweep."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from core.models import SearchTerm
from ingest.runner import build_tier1_adapters, pull_all_sources
from sqlalchemy.orm import Session


@pytest.mark.asyncio
async def test_pull_all_sources_no_terms_runs_sweep(db_session: Session) -> None:
    fake_adapter = MagicMock()
    fake_adapter.source_name = "greenhouse"

    async def fake_fetch(adapter, params, pipeline):
        return [], 0

    with patch("ingest.runner.build_tier2_adapters", return_value=[(fake_adapter, MagicMock())]):
        with patch("ingest.runner._fetch_adapter", side_effect=fake_fetch) as fetch_mock:
            with patch("ingest.runner.RemotiveAdapter") as remotive_cls:
                remotive_cls.return_value.__aenter__ = AsyncMock(return_value=remotive_cls.return_value)
                remotive_cls.return_value.__aexit__ = AsyncMock(return_value=None)
                stats = await pull_all_sources(db_session)

    assert fetch_mock.call_count >= 1
    assert stats["terms_fetched"] == 0


@pytest.mark.asyncio
async def test_pull_all_sources_fetches_per_term(db_session: Session) -> None:
    db_session.add(
        SearchTerm(term="registered nurse", normalized_term="registered nurse", is_active=True)
    )
    db_session.commit()

    async def fake_fetch(adapter, params, pipeline):
        assert len(params.search_terms) == 1
        return [], 0

    with patch("ingest.runner.build_tier1_adapters", return_value=[object()]):
        with patch("ingest.runner._fetch_adapter", side_effect=fake_fetch) as fetch_mock:
            stats = await pull_all_sources(
                db_session,
                search_terms=("registered nurse",),
                subset=True,
            )

    assert fetch_mock.call_count >= 1
    assert stats["terms_fetched"] == 1


@pytest.mark.asyncio
async def test_pull_all_sources_subset_skips_tier2(db_session: Session) -> None:
    with patch("ingest.runner.build_tier1_adapters", return_value=[]):
        with patch("ingest.runner._fetch_adapter", return_value=([], 0)):
            with patch("ingest.runner.build_tier2_adapters") as tier2_mock:
                await pull_all_sources(db_session, search_terms=("nurse",), subset=True)
    tier2_mock.assert_not_called()


@pytest.mark.asyncio
async def test_nightly_does_not_call_freshness(db_session: Session) -> None:
    with patch("ingest.runner._run_nightly_sweep", new_callable=AsyncMock):
        with patch("ingest.runner.apply_freshness_lifecycle") as freshness_mock:
            await pull_all_sources(db_session)
    freshness_mock.assert_not_called()


def test_build_tier1_adapters_omits_jsearch_unless_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JSEARCH_API_KEY", "test-key")
    monkeypatch.delenv("JSEARCH_ENABLED", raising=False)
    adapters = build_tier1_adapters(MagicMock())
    assert all(adapter.source_name != "jsearch" for adapter in adapters)


def test_build_tier1_adapters_includes_jsearch_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JSEARCH_API_KEY", "test-key")
    monkeypatch.setenv("JSEARCH_ENABLED", "true")
    adapters = build_tier1_adapters(MagicMock())
    assert any(adapter.source_name == "jsearch" for adapter in adapters)
