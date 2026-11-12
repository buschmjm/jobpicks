"""Greenhouse adapter tests with mocked HTTP."""

from datetime import date

import httpx
import pytest
import respx
from ingest.adapters.greenhouse import GreenhouseAdapter
from ingest.base import FetchParams
from ingest.html_utils import html_to_plain_text
from ingest.schema import WorkArrangement


def test_html_to_plain_text() -> None:
    assert "Terraform" in html_to_plain_text("<p>Operate <strong>Terraform</strong> clusters.</p>")


@respx.mock
@pytest.mark.asyncio
async def test_greenhouse_fetch_maps_jobs(greenhouse_payload: dict) -> None:
    route = respx.get("https://boards-api.greenhouse.io/v1/boards/hashicorp/jobs").mock(
        return_value=httpx.Response(200, json=greenhouse_payload)
    )

    async with GreenhouseAdapter(board_token="hashicorp", company_name="HashiCorp") as adapter:
        result = await adapter.fetch(FetchParams(max_days_old=28))

    assert route.called
    request = route.calls[0].request
    assert request.headers["User-Agent"]
    assert "content=true" in str(request.url)
    assert len(result.jobs) == 1
    job = result.jobs[0]
    assert job.title == "Senior Site Reliability Engineer"
    assert job.company == "HashiCorp"
    assert job.location == "Remote - US"
    assert job.remote is True
    assert job.work_arrangement == WorkArrangement.REMOTE
    assert job.source == "greenhouse"
    assert "<p>" in job.description
    assert "Terraform" in job.description
    assert job.date_posted == date(2026, 8, 20)
    assert result.filtered_out == 1


@respx.mock
@pytest.mark.asyncio
async def test_greenhouse_requires_board_token() -> None:
    async with GreenhouseAdapter(company_name="HashiCorp") as adapter:
        with pytest.raises(ValueError, match="board_token"):
            await adapter.fetch(FetchParams())
