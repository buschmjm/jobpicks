"""Adzuna adapter tests with mocked HTTP."""

from datetime import date

import httpx
import pytest
import respx
from ingest.adapters.adzuna import AdzunaAdapter
from ingest.base import FetchParams


@pytest.fixture
def adzuna_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADZUNA_APP_ID", "test-app-id")
    monkeypatch.setenv("ADZUNA_APP_KEY", "test-app-key")


@respx.mock
@pytest.mark.asyncio
async def test_adzuna_fetch_maps_jobs(adzuna_env: None, adzuna_payload: dict) -> None:
    route = respx.get(url__regex=r"https://api\.adzuna\.com/v1/api/jobs/us/search/\d+").mock(
        return_value=httpx.Response(200, json=adzuna_payload)
    )

    async with AdzunaAdapter() as adapter:
        result = await adapter.fetch(
            FetchParams(
                search_terms=("platform engineer", "devops"),
                salary_min=120000,
                max_days_old=28,
                page=1,
            )
        )

    assert route.called
    assert len(result.jobs) == 1
    job = result.jobs[0]
    assert job.title == "Senior Platform Engineer"
    assert job.company == "Acme Corp"
    assert job.source == "adzuna"
    assert job.salary is not None
    assert job.salary.min_amount == 140000
    assert job.date_posted == date(2026, 8, 20)
    assert result.filtered_out == 1


@respx.mock
@pytest.mark.asyncio
async def test_adzuna_safety_net_filters_salary(adzuna_env: None, adzuna_payload: dict) -> None:
    respx.get(url__regex=r"https://api\.adzuna\.com/v1/api/jobs/us/search/\d+").mock(
        return_value=httpx.Response(200, json=adzuna_payload)
    )

    async with AdzunaAdapter() as adapter:
        result = await adapter.fetch(
            FetchParams(
                search_terms=("platform engineer",),
                salary_min=150000,
                max_days_old=28,
            )
        )

    assert result.jobs == []
    assert result.filtered_out == 2


@respx.mock
@pytest.mark.asyncio
async def test_adzuna_builds_what_or_and_max_days_old(adzuna_env: None, adzuna_payload: dict) -> None:
    route = respx.get(url__regex=r"https://api\.adzuna\.com/v1/api/jobs/us/search/1").mock(
        return_value=httpx.Response(200, json=adzuna_payload)
    )

    async with AdzunaAdapter() as adapter:
        await adapter.fetch(
            FetchParams(
                search_terms=("sre", "platform"),
                max_days_old=28,
                salary_min=100000,
            )
        )

    request = route.calls[0].request
    assert "what_or=sre+platform" in str(request.url) or "what_or=sre%20platform" in str(request.url)
    assert "max_days_old=28" in str(request.url)
    assert "salary_min=100000" in str(request.url)


def test_adzuna_requires_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ADZUNA_APP_ID", raising=False)
    monkeypatch.delenv("ADZUNA_APP_KEY", raising=False)
    with pytest.raises(ValueError, match="ADZUNA_APP_ID"):
        AdzunaAdapter()
