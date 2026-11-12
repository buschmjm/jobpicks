"""Remotive adapter tests with mocked HTTP."""

from datetime import date

import httpx
import pytest
import respx
from ingest.adapters.remotive import RemotiveAdapter, _parse_salary_string
from ingest.base import FetchParams
from ingest.html_utils import html_to_plain_text
from ingest.schema import WorkArrangement


def test_html_to_plain_text() -> None:
    assert "Kubernetes" in html_to_plain_text("<p>Lead <strong>Kubernetes</strong> work.</p>")


def test_parse_salary_string() -> None:
    salary = _parse_salary_string("$130,000 - $160,000")
    assert salary is not None
    assert salary.min_amount == 130000
    assert salary.max_amount == 160000


@respx.mock
@pytest.mark.asyncio
async def test_remotive_fetch_maps_jobs(remotive_payload: dict) -> None:
    route = respx.get("https://remotive.com/api/remote-jobs").mock(
        return_value=httpx.Response(200, json=remotive_payload)
    )

    async with RemotiveAdapter() as adapter:
        result = await adapter.fetch(
            FetchParams(
                search_terms=("devops",),
                max_days_old=28,
            )
        )

    assert route.called
    assert "search=devops" in str(route.calls[0].request.url)
    assert len(result.jobs) == 1
    job = result.jobs[0]
    assert job.title == "Senior DevOps Engineer"
    assert job.company == "CloudNative Inc"
    assert job.remote is True
    assert job.work_arrangement == WorkArrangement.REMOTE
    assert job.salary is not None
    assert job.salary.min_amount == 130000
    assert job.date_posted == date(2026, 8, 22)
    assert result.filtered_out == 1


@respx.mock
@pytest.mark.asyncio
async def test_remotive_safety_net_age_filter(remotive_payload: dict) -> None:
    respx.get("https://remotive.com/api/remote-jobs").mock(
        return_value=httpx.Response(200, json=remotive_payload)
    )

    async with RemotiveAdapter() as adapter:
        result = await adapter.fetch(FetchParams(max_days_old=14))

    assert len(result.jobs) == 1
    assert result.filtered_out == 1
