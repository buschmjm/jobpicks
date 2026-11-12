"""Lever public Postings API adapter (plan §8, Tier 2)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import urlencode

import httpx
from core.apply.ats_detect import enrich_standard_job_apply

from ingest.base import FetchParams, FetchResult, SourceAdapter
from ingest.country import resolve_job_country
from ingest.quota import QuotaTracker
from ingest.rate_limit import DEFAULT_USER_AGENT, HostRateLimiter
from ingest.schema import EmploymentType, SalaryInfo, StandardJob, WorkArrangement

LEVER_HOST = "api.lever.co"
LEVER_BASE = f"https://{LEVER_HOST}/v0/postings"


def _parse_timestamp_ms(value: int | float | None, fallback: datetime) -> date:
    if value is None:
        return fallback.date()
    try:
        return datetime.fromtimestamp(float(value) / 1000.0, tz=UTC).date()
    except (ValueError, OSError, OverflowError):
        return fallback.date()


def _build_description(record: dict[str, Any]) -> str:
    parts: list[str] = []
    plain = (record.get("descriptionPlain") or record.get("description") or "").strip()
    if plain:
        parts.append(plain)
    for section in record.get("lists") or []:
        if not isinstance(section, dict):
            continue
        heading = (section.get("text") or "").strip()
        content = (section.get("content") or "").strip()
        if heading and content:
            parts.append(f"{heading}\n{content}")
        elif content:
            parts.append(content)
    if parts:
        return "\n\n".join(parts)
    return record.get("text") or "No description provided."


def _parse_salary(record: dict[str, Any]) -> SalaryInfo | None:
    salary_range = record.get("salaryRange") or record.get("salary")
    if not isinstance(salary_range, dict):
        return None
    min_amount = salary_range.get("min")
    max_amount = salary_range.get("max")
    if min_amount is None and max_amount is None:
        return None
    currency = salary_range.get("currency") or salary_range.get("currencyCode") or "USD"
    interval = (salary_range.get("interval") or salary_range.get("period") or "year").lower()
    period = "year" if "year" in interval else interval
    return SalaryInfo(
        min_amount=float(min_amount) if min_amount is not None else None,
        max_amount=float(max_amount) if max_amount is not None else None,
        currency=str(currency),
        period=period,
    )


def _map_commitment(raw: str | None) -> EmploymentType:
    if not raw:
        return EmploymentType.UNKNOWN
    normalized = raw.lower()
    if "full" in normalized:
        return EmploymentType.FULL_TIME
    if "part" in normalized:
        return EmploymentType.PART_TIME
    if "contract" in normalized or "temp" in normalized:
        return EmploymentType.CONTRACT
    if "intern" in normalized:
        return EmploymentType.INTERNSHIP
    return EmploymentType.UNKNOWN


def _map_workplace_type(raw: str | None) -> WorkArrangement:
    if not raw:
        return WorkArrangement.UNKNOWN
    normalized = raw.lower()
    if normalized == "remote":
        return WorkArrangement.REMOTE
    if normalized == "hybrid":
        return WorkArrangement.HYBRID
    if normalized in {"onsite", "on-site", "on_site"}:
        return WorkArrangement.ONSITE
    return WorkArrangement.UNKNOWN


def _map_remote(work_arrangement: WorkArrangement, location: str) -> bool | None:
    if work_arrangement == WorkArrangement.REMOTE:
        return True
    if work_arrangement == WorkArrangement.ONSITE:
        return False
    if "remote" in location.lower():
        return True
    return None


def _format_location(categories: dict[str, Any]) -> str:
    primary = (categories.get("location") or "").strip()
    extras = categories.get("allLocations") or []
    extra_locations = [str(item).strip() for item in extras if str(item).strip()] if isinstance(extras, list) else []
    parts = [primary] if primary else []
    for loc in extra_locations:
        if loc not in parts:
            parts.append(loc)
    return " | ".join(parts) if parts else "Unknown"


def _map_lever_record(
    record: dict[str, Any],
    *,
    company_name: str,
    collected_at: datetime,
) -> StandardJob:
    categories = record.get("categories") or {}
    if not isinstance(categories, dict):
        categories = {}
    location = _format_location(categories)
    description = _build_description(record)
    work_arrangement = _map_workplace_type(record.get("workplaceType"))
    remote = _map_remote(work_arrangement, location)

    source_url = (record.get("hostedUrl") or record.get("applyUrl") or "").strip()
    apply_url, ats_type, ats_metadata = enrich_standard_job_apply(source_url=source_url)

    return StandardJob(
        title=record.get("text") or "Untitled",
        company=company_name,
        location=location,
        remote=remote,
        latitude=None,
        longitude=None,
        employment_type=_map_commitment(categories.get("commitment")),
        salary=_parse_salary(record),
        date_posted=_parse_timestamp_ms(record.get("createdAt"), collected_at),
        description=description,
        requirements=None,
        source="lever",
        source_url=source_url,
        collected_timestamp=collected_at,
        apply_url=apply_url,
        ats_type=ats_type,
        ats_metadata=ats_metadata,
        source_id=str(record.get("id")) if record.get("id") is not None else None,
        country=resolve_job_country(country=None, location=location),
        work_arrangement=work_arrangement,
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


class LeverAdapter(SourceAdapter):
    """Lever public Postings API — JSON feed per company site slug."""

    source_name = "lever"

    def __init__(
        self,
        *,
        site_slug: str | None = None,
        company_name: str | None = None,
        client: httpx.AsyncClient | None = None,
        quota: QuotaTracker | None = None,
        rate_limiter: HostRateLimiter | None = None,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        super().__init__(client=client, quota=quota)
        self.site_slug = site_slug
        self.company_name = company_name
        self.rate_limiter = rate_limiter or HostRateLimiter()
        self.user_agent = user_agent

    def _resolve_site_slug(self, params: FetchParams) -> str:
        slug = params.extra.get("site_slug") or self.site_slug
        if not slug:
            msg = "site_slug must be set on adapter or FetchParams.extra"
            raise ValueError(msg)
        return str(slug)

    def _resolve_company_name(self, params: FetchParams) -> str:
        name = params.extra.get("company_name") or self.company_name
        if not name:
            msg = "company_name must be set on adapter or FetchParams.extra"
            raise ValueError(msg)
        return str(name)

    def _build_url(self, site_slug: str, params: FetchParams) -> str:
        query: dict[str, str | int] = {"mode": "json"}
        if params.results_per_page:
            query["limit"] = min(params.results_per_page, 100)
        if params.search_terms:
            query["department"] = " ".join(params.search_terms)
        encoded = urlencode(query)
        return f"{LEVER_BASE}/{site_slug}?{encoded}"

    async def fetch(self, params: FetchParams) -> FetchResult:
        self._reserve_quota(1)
        site_slug = self._resolve_site_slug(params)
        company_name = self._resolve_company_name(params)
        client = await self._get_client()

        await self.rate_limiter.wait(LEVER_HOST)
        url = self._build_url(site_slug, params)
        response = await client.get(url, headers={"User-Agent": self.user_agent})
        response.raise_for_status()
        payload = response.json()

        collected_at = self.utc_now()
        reference = collected_at.date()
        jobs: list[StandardJob] = []
        filtered_out = 0

        records = payload if isinstance(payload, list) else payload.get("data") or []
        for record in records:
            job = _map_lever_record(record, company_name=company_name, collected_at=collected_at)
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
            page=1,
            total_available=len(records),
            filtered_out=filtered_out,
            raw_pages=[{"data": records}],
        )
