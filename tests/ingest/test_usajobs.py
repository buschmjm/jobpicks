"""USAJOBS adapter tests with mocked HTTP."""

from datetime import date

import httpx
import pytest
import respx
from ingest.adapters.usajobs import USAJobsAdapter
from ingest.base import FetchParams
from ingest.schema import WorkArrangement


@respx.mock
@pytest.mark.asyncio
async def test_usajobs_fetch_maps_jobs(usajobs_payload: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USAJOBS_API_KEY", "test-api-key")
    monkeypatch.setenv("USAJOBS_USER_AGENT", "test@example.com")

    route = respx.get("https://data.usajobs.gov/api/search").mock(
        return_value=httpx.Response(200, json=usajobs_payload)
    )

    async with USAJobsAdapter() as adapter:
        result = await adapter.fetch(
            FetchParams(
                search_terms=("DevOps",),
                extra={"location": "Remote"},
                max_days_old=28,
            )
        )

    assert route.called
    request = route.calls[0].request
    assert request.headers["Host"] == "data.usajobs.gov"
    assert request.headers["Authorization-Key"] == "test-api-key"
    assert request.headers["User-Agent"] == "test@example.com"
    assert "Keyword=DevOps" in str(request.url)
    assert "LocationName=Remote" in str(request.url)
    assert len(result.jobs) == 1
    job = result.jobs[0]
    assert job.title == "DevOps Engineer"
    assert job.company == "Department of Veterans Affairs"
    assert job.remote is True
    assert job.work_arrangement == WorkArrangement.REMOTE
    assert job.salary is not None
    assert job.salary.min_amount == 95000
    assert job.date_posted == date(2026, 8, 18)
    assert job.source == "usajobs"
    assert result.filtered_out == 1


def test_usajobs_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("USAJOBS_API_KEY", raising=False)
    with pytest.raises(ValueError, match="USAJOBS_API_KEY"):
        USAJobsAdapter()


@respx.mock
@pytest.mark.asyncio
async def test_usajobs_fetch_handles_bool_telework(usajobs_payload: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USAJOBS_API_KEY", "test-api-key")
    monkeypatch.setenv("USAJOBS_USER_AGENT", "test@example.com")

    item = usajobs_payload["SearchResult"]["SearchResultItems"][0]
    item["MatchedObjectDescriptor"]["UserArea"]["Details"]["TeleworkEligible"] = True

    respx.get("https://data.usajobs.gov/api/search").mock(
        return_value=httpx.Response(200, json=usajobs_payload)
    )

    async with USAJobsAdapter() as adapter:
        result = await adapter.fetch(FetchParams(search_terms=("DevOps",), max_days_old=28))

    assert len(result.jobs) == 1
    assert result.jobs[0].remote is True
    assert result.jobs[0].work_arrangement == WorkArrangement.REMOTE
