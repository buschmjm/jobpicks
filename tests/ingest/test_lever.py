"""Lever adapter tests with mocked HTTP."""

from datetime import date

import httpx
import pytest
import respx
from ingest.adapters.lever import LeverAdapter, _build_description
from ingest.base import FetchParams
from ingest.schema import WorkArrangement


def test_build_description_includes_lists() -> None:
    text = _build_description(
        {
            "descriptionPlain": "Platform team role.",
            "lists": [{"text": "Requirements", "content": "Kubernetes experience."}],
        }
    )
    assert "Platform team role." in text
    assert "Kubernetes experience." in text


@respx.mock
@pytest.mark.asyncio
async def test_lever_fetch_maps_jobs(lever_payload: list) -> None:
    route = respx.get("https://api.lever.co/v0/postings/elastic").mock(
        return_value=httpx.Response(200, json=lever_payload)
    )

    async with LeverAdapter(site_slug="elastic", company_name="Elastic") as adapter:
        result = await adapter.fetch(FetchParams(max_days_old=28))

    assert route.called
    request = route.calls[0].request
    assert request.headers["User-Agent"]
    assert "mode=json" in str(request.url)
    assert len(result.jobs) == 1
    job = result.jobs[0]
    assert job.title == "Staff Platform Engineer"
    assert job.company == "Elastic"
    assert job.remote is True
    assert job.work_arrangement == WorkArrangement.REMOTE
    assert job.salary is not None
    assert job.salary.min_amount == 180000
    assert job.date_posted == date(2026, 8, 20)
    assert job.source == "lever"
    assert result.filtered_out == 1


@respx.mock
@pytest.mark.asyncio
async def test_lever_requires_site_slug() -> None:
    async with LeverAdapter(company_name="Elastic") as adapter:
        with pytest.raises(ValueError, match="site_slug"):
            await adapter.fetch(FetchParams())
