"""JSearch adapter tests — deterministic mapping, quota enforcement."""

from datetime import UTC, date

import httpx
import pytest
import respx
from ingest.adapters.jsearch import JSearchAdapter, _map_jsearch_record
from ingest.base import FetchParams
from ingest.quota import QuotaBudget, QuotaExceededError, QuotaTracker
from ingest.schema import WorkArrangement


@pytest.fixture
def jsearch_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JSEARCH_API_KEY", "test-jsearch-key")


def test_jsearch_null_remote_is_unknown(jsearch_payload: dict) -> None:
    record = jsearch_payload["data"][1]
    from datetime import datetime

    job = _map_jsearch_record(record, datetime(2026, 8, 27, tzinfo=UTC))
    assert job.remote is None
    assert job.work_arrangement == WorkArrangement.HYBRID


def test_jsearch_deterministic_mapping(jsearch_payload: dict) -> None:
    from datetime import datetime

    record = jsearch_payload["data"][0]
    job = _map_jsearch_record(record, datetime(2026, 8, 27, tzinfo=UTC))

    assert job.title == "Senior Platform Engineer"
    assert job.company == "Acme Corp"
    assert job.remote is True
    assert job.seniority_level == "senior"
    assert job.required_experience_years == 5
    assert job.required_technologies == ("Kubernetes", "Terraform", "Python")
    assert job.benefits == ("health_insurance", "401k")
    assert job.requirements is not None
    assert "Kubernetes" in job.requirements
    assert job.date_posted == date(2026, 8, 21)


@respx.mock
@pytest.mark.asyncio
async def test_jsearch_fetch_with_mock(jsearch_env: None, jsearch_payload: dict) -> None:
    route = respx.get(url__regex=r"https://api\.openwebninja\.com/jsearch/search-v2.*").mock(
        return_value=httpx.Response(200, json=jsearch_payload)
    )

    async with JSearchAdapter(max_pages=1) as adapter:
        result = await adapter.fetch(
            FetchParams(
                search_terms=("platform engineer",),
                salary_min=100000,
                max_days_old=28,
            )
        )

    assert route.called
    assert len(result.jobs) == 1
    assert result.requests_used == 1
    assert result.filtered_out == 2
    assert result.jobs[0].source == "jsearch"
    assert "X-API-Key" in route.calls[0].request.headers


@respx.mock
@pytest.mark.asyncio
async def test_jsearch_quota_enforcement(jsearch_env: None, jsearch_payload: dict) -> None:
    respx.get(url__regex=r"https://api\.openwebninja\.com/jsearch/search-v2.*").mock(
        return_value=httpx.Response(200, json=jsearch_payload)
    )

    tracker = QuotaTracker()
    tracker.register(QuotaBudget(source="jsearch", daily_limit=1))

    async with JSearchAdapter(quota=tracker, max_pages=2) as adapter:
        first = await adapter.fetch(FetchParams(search_terms=("devops",)))
        assert first.requests_used == 1
        assert tracker.remaining("jsearch") == 0

        with pytest.raises(QuotaExceededError):
            await adapter.fetch(FetchParams(search_terms=("sre",)))


@pytest.mark.asyncio
async def test_jsearch_raises_when_quota_exhausted_before_fetch(jsearch_env: None) -> None:
    tracker = QuotaTracker()
    tracker.register(QuotaBudget(source="jsearch", daily_limit=1))
    tracker.consume("jsearch")

    async with JSearchAdapter(quota=tracker) as adapter:
        with pytest.raises(QuotaExceededError):
            await adapter.fetch(FetchParams(search_terms=("devops",)))


@respx.mock
@pytest.mark.asyncio
async def test_jsearch_remote_only_safety_net(jsearch_env: None, jsearch_payload: dict) -> None:
    respx.get(url__regex=r"https://api\.openwebninja\.com/jsearch/search-v2.*").mock(
        return_value=httpx.Response(200, json=jsearch_payload)
    )

    async with JSearchAdapter(max_pages=1) as adapter:
        result = await adapter.fetch(
            FetchParams(
                search_terms=("engineer",),
                max_days_old=28,
                remote_only=True,
            )
        )

    assert all(job.remote is not False for job in result.jobs)
    assert result.filtered_out >= 1


def test_jsearch_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JSEARCH_API_KEY", raising=False)
    with pytest.raises(ValueError, match="JSEARCH_API_KEY"):
        JSearchAdapter()
