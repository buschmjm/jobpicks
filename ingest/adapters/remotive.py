"""Remotive free JSON API adapter (plan §8)."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any
from urllib.parse import urlencode

from ingest.base import FetchParams, FetchResult, SourceAdapter
from ingest.country import is_us_job, resolve_job_country
from ingest.html_utils import html_to_plain_text
from ingest.schema import EmploymentType, SalaryInfo, StandardJob, WorkArrangement

REMOTIVE_BASE = "https://remotive.com/api/remote-jobs"


def _parse_publication_date(value: str, fallback: datetime) -> date:
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return fallback.date()


def _parse_salary_string(raw: str | None) -> SalaryInfo | None:
    if not raw:
        return None
    numbers = [float(n.replace(",", "")) for n in re.findall(r"[\d,]+(?:\.\d+)?", raw)]
    if not numbers:
        return SalaryInfo(raw=raw.strip())
    min_amount = numbers[0]
    max_amount = numbers[1] if len(numbers) > 1 else numbers[0]
    return SalaryInfo(min_amount=min_amount, max_amount=max_amount, currency="USD", period="year", raw=raw)


def _map_job_type(raw: str | None) -> EmploymentType:
    if not raw:
        return EmploymentType.UNKNOWN
    normalized = raw.lower().replace("-", "_")
    mapping = {
        "full_time": EmploymentType.FULL_TIME,
        "part_time": EmploymentType.PART_TIME,
        "contract": EmploymentType.CONTRACT,
        "freelance": EmploymentType.FREELANCE,
        "internship": EmploymentType.INTERNSHIP,
    }
    return mapping.get(normalized, EmploymentType.UNKNOWN)


def _map_remotive_record(record: dict[str, Any], collected_at: datetime) -> StandardJob:
    description_html = (record.get("description") or "").strip()
    description = description_html or html_to_plain_text(description_html)
    location = record.get("candidate_required_location") or "Remote"
    salary = _parse_salary_string(record.get("salary"))
    country = resolve_job_country(country=None, location=location)

    return StandardJob(
        title=record.get("title") or "Untitled",
        company=record.get("company_name") or "Unknown",
        location=location,
        remote=True,
        latitude=None,
        longitude=None,
        employment_type=_map_job_type(record.get("job_type")),
        salary=salary,
        date_posted=_parse_publication_date(
            record.get("publication_date") or collected_at.isoformat(),
            collected_at,
        ),
        description=description,
        requirements=None,
        source="remotive",
        source_url=record.get("url") or "",
        collected_timestamp=collected_at,
        source_id=str(record.get("id")) if record.get("id") is not None else None,
        country=country,
        work_arrangement=WorkArrangement.REMOTE,
        raw_payload=record,
    )


def _passes_safety_net(
    job: StandardJob,
    *,
    salary_min: int | None,
    max_days_old: int,
    reference: date,
) -> bool:
    age = (reference - job.date_posted).days
    if age > max_days_old or age < 0:
        return False
    if salary_min is not None and job.salary is not None:
        effective = job.salary.min_amount
        if effective is not None and effective < salary_min:
            return False
    return is_us_job(job)


class RemotiveAdapter(SourceAdapter):
    """Remotive API — remote jobs with optional search filter."""

    source_name = "remotive"

    async def fetch(self, params: FetchParams) -> FetchResult:
        self._reserve_quota(1)
        client = await self._get_client()

        query: dict[str, str | int] = {}
        if params.search_terms:
            query["search"] = " ".join(params.search_terms)
        if params.results_per_page:
            query["limit"] = min(params.results_per_page, 100)

        url = REMOTIVE_BASE
        if query:
            url = f"{url}?{urlencode(query)}"

        response = await client.get(url)
        response.raise_for_status()
        payload = response.json()

        collected_at = self.utc_now()
        reference = collected_at.date()
        jobs: list[StandardJob] = []
        filtered_out = 0

        for record in payload.get("jobs") or []:
            job = _map_remotive_record(record, collected_at)
            if _passes_safety_net(
                job,
                salary_min=params.salary_min,
                max_days_old=params.max_days_old,
                reference=reference,
            ):
                jobs.append(job)
            else:
                filtered_out += 1

        return FetchResult(
            jobs=jobs,
            source=self.source_name,
            requests_used=1,
            page=1,
            total_available=payload.get("job-count"),
            filtered_out=filtered_out,
            raw_pages=[payload],
        )
