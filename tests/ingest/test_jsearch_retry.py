"""Tests for JSearch retry and error parsing."""

from __future__ import annotations

import httpx
import pytest
import respx
from ingest.adapters.jsearch import JSearchAdapter
from ingest.adapters.jsearch_errors import JSearchRequestError, parse_jsearch_error
from ingest.base import FetchParams


@pytest.fixture
def jsearch_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JSEARCH_API_KEY", "test-jsearch-key")


def test_parse_jsearch_error_includes_status_and_message() -> None:
    response = httpx.Response(
        429,
        json={"message": "Rate limit exceeded"},
        headers={"Retry-After": "2"},
        request=httpx.Request("GET", "https://api.openwebninja.com/jsearch/search-v2"),
    )
    err = parse_jsearch_error(response)
    assert err.status_code == 429
    assert "Rate limit" in err.message
    assert err.retry_after == 2.0


@respx.mock
@pytest.mark.asyncio
async def test_jsearch_retries_on_429(jsearch_env: None, jsearch_payload: dict) -> None:
    route = respx.get(url__regex=r"https://api\.openwebninja\.com/jsearch/search-v2.*")
    route.side_effect = [
        httpx.Response(429, json={"message": "slow down"}, headers={"Retry-After": "0"}),
        httpx.Response(200, json=jsearch_payload),
    ]

    async with JSearchAdapter(max_pages=1) as adapter:
        result = await adapter.fetch(FetchParams(search_terms=("devops",)))

    assert route.call_count == 2
    assert result.requests_used == 1
    assert len(result.jobs) >= 1


@respx.mock
@pytest.mark.asyncio
async def test_jsearch_raises_structured_error_after_retries(jsearch_env: None) -> None:
    respx.get(url__regex=r"https://api\.openwebninja\.com/jsearch/search-v2.*").mock(
        return_value=httpx.Response(429, json={"message": "quota exceeded"})
    )

    async with JSearchAdapter(max_pages=1) as adapter:
        with pytest.raises(JSearchRequestError) as exc_info:
            await adapter.fetch(FetchParams(search_terms=("devops",)))
    assert exc_info.value.status_code == 429
