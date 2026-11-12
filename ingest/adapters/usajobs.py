"""USAJOBS official Search API adapter (plan §8, Tier 2)."""

from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any
from urllib.parse import urlencode

import httpx

from ingest.base import FetchParams, FetchResult, SourceAdapter
from ingest.quota import QuotaTracker
from ingest.rate_limit import DEFAULT_USER_AGENT, HostRateLimiter
from ingest.schema import EmploymentType, SalaryInfo, StandardJob, WorkArrangement

USAJOBS_HOST = "data.usajobs.gov"
USAJOBS_BASE = f"https://{USAJOBS_HOST}/api/search"


def _parse_date(value: str | None, fallback: datetime) -> date:
    if not value:
        return fallback.date()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return fallback.date()


def _parse_salary(min_value: str | float | None, max_value: str | float | None) -> SalaryInfo | None:
    if min_value is None and max_value is None:
        return None
    min_amount = float(min_value) if min_value not in (None, "") else None
    max_amount = float(max_value) if max_value not in (None, "") else None
    if min_amount is None and max_amount is None:
        return None
    return SalaryInfo(
        min_amount=min_amount,
        max_amount=max_amount,
        currency="USD",
        period="year",
    )


def _map_remote(telework_eligible: str | bool | None, location: str) -> bool | None:
    if isinstance(telework_eligible, bool):
        return telework_eligible
    if telework_eligible:
        normalized = str(telework_eligible).lower()
        if normalized in {"yes", "true", "eligible"}:
            return True
        if normalized in {"no", "false", "not eligible"}:
            return False
    if "remote" in location.lower() or "telework" in location.lower():
        return True
    return None


def _map_work_arrangement(
    telework_eligible: str | bool | None, location: str, remote: bool | None
) -> WorkArrangement:
    if remote is True:
        return WorkArrangement.REMOTE
    if remote is False:
        return WorkArrangement.ONSITE
    if isinstance(telework_eligible, bool):
        return WorkArrangement.REMOTE if telework_eligible else WorkArrangement.ONSITE
    if telework_eligible and str(telework_eligible).lower() in {"yes", "true", "eligible"}:
        return WorkArrangement.REMOTE
    if "remote" in location.lower():
        return WorkArrangement.REMOTE
    return WorkArrangement.UNKNOWN


def _map_employment_type(raw: str | None) -> EmploymentType:
    if not raw:
        return EmploymentType.UNKNOWN
    normalized = raw.lower()
    if "full" in normalized:
        return EmploymentType.FULL_TIME
    if "part" in normalized:
        return EmploymentType.PART_TIME
    if "intermittent" in normalized or "temp" in normalized:
        return EmploymentType.TEMPORARY
    return EmploymentType.UNKNOWN


def _map_usajobs_record(record: dict[str, Any], collected_at: datetime) -> StandardJob:
    descriptor = record.get("MatchedObjectDescriptor") or record
    locations = descriptor.get("PositionLocation") or []
    if locations and isinstance(locations[0], dict):
        location = locations[0].get("LocationName") or "United States"
    else:
        location = "United States"

    remuneration = descriptor.get("PositionRemuneration") or []
    salary_min: str | float | None = None
    salary_max: str | float | None = None
    if remuneration and isinstance(remuneration[0], dict):
        salary_min = remuneration[0].get("MinimumRange")
        salary_max = remuneration[0].get("MaximumRange")

    user_area = descriptor.get("UserArea") or {}
    details = user_area.get("Details") or {}
    telework = details.get("TeleworkEligible")
    description = (
        descriptor.get("QualificationSummary")
        or descriptor.get("UserArea", {}).get("Details", {}).get("MajorDuties")
        or descriptor.get("PositionFormattedDescription", [{}])[0].get("Content", "")
        or descriptor.get("PositionTitle")
        or "No description provided."
    )
    if isinstance(description, list):
        description = "\n".join(str(item) for item in description)

    remote = _map_remote(telework, location)
    company = descriptor.get("OrganizationName") or "U.S. Federal Government"

    apply_uri = descriptor.get("ApplyURI")
    source_url = apply_uri[0] if isinstance(apply_uri, list) and apply_uri else descriptor.get("PositionURI") or ""

    return StandardJob(
        title=descriptor.get("PositionTitle") or "Untitled",
        company=company,
        location=location,
        remote=remote,
        latitude=None,
        longitude=None,
        employment_type=_map_employment_type(descriptor.get("PositionSchedule", [{}])[0].get("Name")),
        salary=_parse_salary(salary_min, salary_max),
        date_posted=_parse_date(descriptor.get("PublicationStartDate"), collected_at),
        description=str(description),
        requirements=descriptor.get("QualificationSummary"),
        source="usajobs",
        source_url=str(source_url),
        collected_timestamp=collected_at,
        source_id=str(descriptor.get("PositionID")) if descriptor.get("PositionID") is not None else None,
        work_arrangement=_map_work_arrangement(telework, location, remote),
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


class USAJobsAdapter(SourceAdapter):
    """USAJOBS Search API — Keyword and LocationName query parameters."""

    source_name = "usajobs"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        user_agent: str | None = None,
        client: httpx.AsyncClient | None = None,
        quota: QuotaTracker | None = None,
        rate_limiter: HostRateLimiter | None = None,
    ) -> None:
        super().__init__(client=client, quota=quota)
        self.api_key = api_key or os.environ.get("USAJOBS_API_KEY", "")
        self.user_agent = user_agent or os.environ.get("USAJOBS_USER_AGENT", DEFAULT_USER_AGENT)
        self.rate_limiter = rate_limiter or HostRateLimiter()

        if not self.api_key:
            msg = "USAJOBS_API_KEY must be set"
            raise ValueError(msg)

    def _build_url(self, params: FetchParams) -> str:
        query: dict[str, str | int] = {
            "Page": max(1, params.page),
            "ResultsPerPage": min(500, max(1, params.results_per_page)),
        }
        if params.search_terms:
            query["Keyword"] = " ".join(params.search_terms)
        location = params.extra.get("location") or params.extra.get("LocationName")
        if location:
            query["LocationName"] = str(location)
        if params.salary_min is not None:
            query["MinimumPay"] = params.salary_min
        return f"{USAJOBS_BASE}?{urlencode(query)}"

    def _headers(self) -> dict[str, str]:
        return {
            "Host": USAJOBS_HOST,
            "User-Agent": self.user_agent,
            "Authorization-Key": self.api_key,
        }

    async def fetch(self, params: FetchParams) -> FetchResult:
        self._reserve_quota(1)
        client = await self._get_client()

        await self.rate_limiter.wait(USAJOBS_HOST)
        url = self._build_url(params)
        response = await client.get(url, headers=self._headers())
        response.raise_for_status()
        payload = response.json()

        collected_at = self.utc_now()
        reference = collected_at.date()
        search_result = payload.get("SearchResult") or {}
        items = search_result.get("SearchResultItems") or []

        jobs: list[StandardJob] = []
        filtered_out = 0
        for record in items:
            job = _map_usajobs_record(record, collected_at)
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
            total_available=search_result.get("SearchResultCountAll"),
            filtered_out=filtered_out,
            raw_pages=[payload],
        )
