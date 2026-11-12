"""Adzuna aggregator adapter (plan §8, §18)."""

from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any
from urllib.parse import urlencode

import httpx

from ingest.base import FetchParams, FetchResult, SourceAdapter
from ingest.country import DEFAULT_INGEST_COUNTRY
from ingest.quota import QuotaTracker
from ingest.schema import EmploymentType, SalaryInfo, StandardJob

ADZUNA_BASE = "https://api.adzuna.com/v1/api/jobs"
DEFAULT_COUNTRY = "us"


def _parse_date(value: str) -> date:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date()


def _map_employment_type(record: dict[str, Any]) -> EmploymentType:
    contract_time = (record.get("contract_time") or "").lower()
    contract_type = (record.get("contract_type") or "").lower()
    combined = f"{contract_time} {contract_type}"
    if "full" in combined:
        return EmploymentType.FULL_TIME
    if "part" in combined:
        return EmploymentType.PART_TIME
    if "contract" in combined or "temporary" in combined:
        return EmploymentType.CONTRACT
    if "intern" in combined:
        return EmploymentType.INTERNSHIP
    return EmploymentType.UNKNOWN


def _infer_remote(location_display: str, description: str) -> bool | None:
    text = f"{location_display} {description}".lower()
    if "remote" in text or "work from home" in text or "wfh" in text:
        return True
    return None


def _map_adzuna_record(record: dict[str, Any], collected_at: datetime) -> StandardJob:
    location_obj = record.get("location") or {}
    location_display = location_obj.get("display_name") or "Unknown"
    company_obj = record.get("company") or {}
    company = company_obj.get("display_name") or "Unknown"
    description = record.get("description") or ""

    salary_min = record.get("salary_min")
    salary_max = record.get("salary_max")
    salary: SalaryInfo | None = None
    if salary_min is not None or salary_max is not None:
        salary = SalaryInfo(
            min_amount=float(salary_min) if salary_min is not None else None,
            max_amount=float(salary_max) if salary_max is not None else None,
            currency=record.get("salary_currency") or "USD",
            period="year",
        )

    return StandardJob(
        title=record.get("title") or "Untitled",
        company=company,
        location=location_display,
        remote=_infer_remote(location_display, description),
        latitude=record.get("latitude"),
        longitude=record.get("longitude"),
        employment_type=_map_employment_type(record),
        salary=salary,
        date_posted=_parse_date(record.get("created") or collected_at.isoformat()),
        description=description,
        requirements=None,
        source="adzuna",
        source_url=record.get("redirect_url") or "",
        collected_timestamp=collected_at,
        source_id=str(record.get("id")) if record.get("id") is not None else None,
        country=DEFAULT_INGEST_COUNTRY,
        raw_payload=record,
    )


def _passes_safety_net(
    job: StandardJob,
    *,
    salary_min: int | None,
    max_days_old: int,
    remote_only: bool | None,
    reference: date,
) -> bool:
    age = (reference - job.date_posted).days
    if age > max_days_old or age < 0:
        return False
    if salary_min is not None and job.salary is not None:
        effective = job.salary.min_amount
        if effective is not None and effective < salary_min:
            return False
    return not (remote_only is True and job.remote is False)


class AdzunaAdapter(SourceAdapter):
    """Adzuna REST API — what_or, salary_min, max_days_old, paging."""

    source_name = "adzuna"

    def __init__(
        self,
        *,
        app_id: str | None = None,
        app_key: str | None = None,
        country: str = DEFAULT_COUNTRY,
        client: httpx.AsyncClient | None = None,
        quota: QuotaTracker | None = None,
    ) -> None:
        super().__init__(client=client, quota=quota)
        self.app_id = app_id or os.environ.get("ADZUNA_APP_ID", "")
        self.app_key = app_key or os.environ.get("ADZUNA_APP_KEY", "")
        self.country = country

        if not self.app_id or not self.app_key:
            msg = "ADZUNA_APP_ID and ADZUNA_APP_KEY must be set"
            raise ValueError(msg)

    def _build_url(self, params: FetchParams) -> str:
        page = max(1, params.page)
        query: dict[str, str | int | float] = {
            "app_id": self.app_id,
            "app_key": self.app_key,
            "results_per_page": min(50, max(1, params.results_per_page)),
        }
        if params.search_terms:
            query["what_or"] = " ".join(params.search_terms)
        if params.salary_min is not None:
            query["salary_min"] = params.salary_min
        query["max_days_old"] = params.max_days_old
        if params.latitude is not None:
            query["lat"] = params.latitude
        if params.longitude is not None:
            query["lng"] = params.longitude
        if params.radius_km is not None:
            query["distance"] = params.radius_km

        path = f"{ADZUNA_BASE}/{self.country}/search/{page}"
        return f"{path}?{urlencode(query)}"

    async def fetch(self, params: FetchParams) -> FetchResult:
        self._reserve_quota(1)
        client = await self._get_client()
        url = self._build_url(params)
        response = await client.get(url)
        response.raise_for_status()
        payload = response.json()

        collected_at = self.utc_now()
        reference = collected_at.date()
        jobs: list[StandardJob] = []
        filtered_out = 0

        for record in payload.get("results") or []:
            job = _map_adzuna_record(record, collected_at)
            if _passes_safety_net(
                job,
                salary_min=params.salary_min,
                max_days_old=params.max_days_old,
                remote_only=params.remote_only,
                reference=reference,
            ):
                jobs.append(job)
            else:
                filtered_out += 1

        return FetchResult(
            jobs=jobs,
            source=self.source_name,
            requests_used=1,
            page=params.page,
            total_available=payload.get("count"),
            filtered_out=filtered_out,
            raw_pages=[payload],
        )
