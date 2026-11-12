"""JSearch (OpenWeb Ninja) search-v2 adapter — deterministic mapping only (plan §9)."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import urlencode

import httpx
from core.apply.ats_detect import enrich_standard_job_apply, pick_best_jsearch_apply_link

from ingest.adapters.jsearch_errors import JSearchRequestError, parse_jsearch_error
from ingest.base import FetchParams, FetchResult, SourceAdapter
from ingest.country import DEFAULT_INGEST_COUNTRY, normalize_country, resolve_job_country
from ingest.quota import QuotaExceededError, QuotaTracker
from ingest.schema import EmploymentType, SalaryInfo, StandardJob, WorkArrangement

logger = logging.getLogger(__name__)

JSEARCH_BASE = "https://jsearch.p.rapidapi.com/search"
OPENWEBNINJA_BASE = "https://api.openwebninja.com/jsearch/search-v2"


def _jsearch_base_url() -> str:
    if os.environ.get("JSEARCH_USE_RAPIDAPI", "").lower() in {"1", "true", "yes"}:
        return JSEARCH_BASE
    return OPENWEBNINJA_BASE


def _parse_posted_date(record: dict[str, Any], fallback: datetime) -> date:
    iso_value = record.get("job_posted_at_datetime_utc")
    if iso_value:
        return datetime.fromisoformat(str(iso_value).replace("Z", "+00:00")).date()
    timestamp = record.get("job_posted_at_timestamp")
    if timestamp:
        return datetime.fromtimestamp(int(timestamp), tz=UTC).date()
    return fallback.date()


def _map_remote(record: dict[str, Any]) -> bool | None:
    """job_is_remote null = unknown, never treat as onsite (plan §18)."""
    value = record.get("job_is_remote")
    if value is None:
        return None
    return bool(value)


def _map_work_arrangement(record: dict[str, Any], remote: bool | None) -> WorkArrangement:
    raw = (record.get("work_arrangement") or record.get("job_work_arrangement") or "").lower()
    if "remote" in raw:
        return WorkArrangement.REMOTE
    if "hybrid" in raw:
        return WorkArrangement.HYBRID
    if "on-site" in raw or "onsite" in raw or "on site" in raw:
        return WorkArrangement.ONSITE
    if remote is True:
        return WorkArrangement.REMOTE
    if remote is False:
        return WorkArrangement.ONSITE
    return WorkArrangement.UNKNOWN


def _map_employment_type(record: dict[str, Any]) -> EmploymentType:
    raw_types = record.get("job_employment_types") or record.get("job_employment_type")
    if raw_types is None:
        return EmploymentType.UNKNOWN
    if isinstance(raw_types, list):
        combined = " ".join(str(item) for item in raw_types).lower()
    else:
        combined = str(raw_types).lower()
    mapping = {
        "fulltime": EmploymentType.FULL_TIME,
        "full_time": EmploymentType.FULL_TIME,
        "parttime": EmploymentType.PART_TIME,
        "part_time": EmploymentType.PART_TIME,
        "contract": EmploymentType.CONTRACT,
        "contractor": EmploymentType.CONTRACT,
        "temporary": EmploymentType.TEMPORARY,
        "intern": EmploymentType.INTERNSHIP,
        "internship": EmploymentType.INTERNSHIP,
    }
    for key, employment in mapping.items():
        if key in combined:
            return employment
    return EmploymentType.UNKNOWN


def _build_location(record: dict[str, Any]) -> str:
    if record.get("job_location"):
        return str(record["job_location"])
    parts = [
        record.get("job_city"),
        record.get("job_state"),
        record.get("job_country"),
    ]
    cleaned = [str(part) for part in parts if part]
    return ", ".join(cleaned) if cleaned else "Unknown"


def _extract_requirements(record: dict[str, Any]) -> str | None:
    highlights = record.get("job_highlights") or {}
    qualifications = highlights.get("Qualifications") or highlights.get("qualifications")
    if qualifications:
        return "\n".join(str(item) for item in qualifications)
    return None


def _map_salary(record: dict[str, Any]) -> SalaryInfo | None:
    min_salary = record.get("job_min_salary")
    max_salary = record.get("job_max_salary")
    if min_salary is None and max_salary is None:
        return None
    period_raw = (record.get("job_salary_period") or "YEAR").lower()
    period = "year" if "year" in period_raw else period_raw
    return SalaryInfo(
        min_amount=float(min_salary) if min_salary is not None else None,
        max_amount=float(max_salary) if max_salary is not None else None,
        currency=record.get("job_salary_currency") or "USD",
        period=period,
    )


def _map_jsearch_record(record: dict[str, Any], collected_at: datetime) -> StandardJob:
    remote = _map_remote(record)
    technologies = record.get("required_technologies") or record.get("job_required_skills") or ()
    if isinstance(technologies, str):
        technologies = (technologies,)
    benefits = record.get("job_benefits") or ()
    if benefits is None:
        benefits = ()

    apply_link = record.get("job_apply_link") or ""
    apply_options = record.get("apply_options") or []
    if not apply_link and apply_options:
        apply_link = apply_options[0].get("apply_link") or ""

    google_link = record.get("job_google_link")
    best_apply, ats_type, ats_metadata = pick_best_jsearch_apply_link(
        apply_link=str(apply_link),
        apply_options=apply_options if isinstance(apply_options, list) else [],
        google_link=str(google_link) if google_link else None,
    )
    source_url = str(apply_link or google_link or best_apply or "").strip()
    apply_url, ats_type, ats_metadata = enrich_standard_job_apply(
        source_url=source_url,
        apply_url=best_apply,
        ats_type=ats_type,
        ats_metadata=ats_metadata,
    )
    if apply_options:
        ats_metadata = {**ats_metadata, "apply_options": apply_options}

    location = _build_location(record)
    raw_country = record.get("job_country")
    country = resolve_job_country(
        country=normalize_country(str(raw_country)) if raw_country else DEFAULT_INGEST_COUNTRY,
        location=location,
    )

    return StandardJob(
        title=record.get("job_title") or "Untitled",
        company=record.get("employer_name") or "Unknown",
        location=location,
        remote=remote,
        latitude=record.get("job_latitude"),
        longitude=record.get("job_longitude"),
        employment_type=_map_employment_type(record),
        salary=_map_salary(record),
        date_posted=_parse_posted_date(record, collected_at),
        description=record.get("job_description") or "",
        requirements=_extract_requirements(record),
        source="jsearch",
        source_url=source_url,
        collected_timestamp=collected_at,
        apply_url=apply_url,
        ats_type=ats_type,
        ats_metadata=ats_metadata,
        source_id=record.get("job_id"),
        country=country,
        work_arrangement=_map_work_arrangement(record, remote),
        seniority_level=record.get("job_seniority_level") or record.get("seniority_level"),
        required_experience_years=_coerce_int(
            record.get("required_experience_years")
            or record.get("job_required_experience")
        ),
        required_technologies=tuple(str(item) for item in technologies),
        benefits=tuple(str(item) for item in benefits if item),
        publisher=record.get("job_publisher"),
        raw_payload=record,
    )


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        digits = "".join(ch for ch in value if ch.isdigit())
        return int(digits) if digits else None
    return None


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


def _date_posted_param(max_days_old: int) -> str:
    if max_days_old <= 1:
        return "today"
    if max_days_old <= 3:
        return "3days"
    if max_days_old <= 7:
        return "week"
    return "month"


def _inter_request_delay_seconds() -> float:
    raw = os.environ.get("JSEARCH_INTER_REQUEST_DELAY_SECONDS", "0.35")
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 0.35


def _max_retries() -> int:
    raw = os.environ.get("JSEARCH_MAX_RETRIES", "3")
    try:
        return max(1, int(raw))
    except ValueError:
        return 3


class JSearchAdapter(SourceAdapter):
    """JSearch search-v2 — deterministic field mapping, quota budget enforcement."""

    source_name = "jsearch"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        client: httpx.AsyncClient | None = None,
        quota: QuotaTracker | None = None,
        max_pages: int = 3,
    ) -> None:
        super().__init__(client=client, quota=quota)
        self.api_key = api_key or os.environ.get("JSEARCH_API_KEY", "")
        self.max_pages = max(1, max_pages)
        if not self.api_key:
            msg = "JSEARCH_API_KEY must be set"
            raise ValueError(msg)

    def _headers(self) -> dict[str, str]:
        if os.environ.get("JSEARCH_USE_RAPIDAPI", "").lower() in {"1", "true", "yes"}:
            return {
                "X-RapidAPI-Key": self.api_key,
                "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
            }
        return {"X-API-Key": self.api_key}

    async def _get_with_retry(self, client: httpx.AsyncClient, url: str) -> httpx.Response:
        headers = self._headers()
        last_error: JSearchRequestError | None = None
        for attempt in range(1, _max_retries() + 1):
            response = await client.get(url, headers=headers)
            if response.status_code < 400:
                return response

            last_error = parse_jsearch_error(response)
            retryable = response.status_code in {429, 500, 502, 503, 504}
            if not retryable or attempt >= _max_retries():
                logger.warning(
                    "jsearch request failed status=%s attempt=%d/%d url=%s message=%s",
                    response.status_code,
                    attempt,
                    _max_retries(),
                    url,
                    last_error.message,
                )
                response.raise_for_status()

            wait_seconds = last_error.retry_after
            if wait_seconds is None:
                wait_seconds = min(30.0, 2.0 ** attempt)
            logger.warning(
                "jsearch rate limited status=%s attempt=%d/%d retry_in=%.1fs url=%s",
                response.status_code,
                attempt,
                _max_retries(),
                wait_seconds,
                url,
            )
            await asyncio.sleep(wait_seconds)

        assert last_error is not None
        raise last_error

    def _build_url(self, params: FetchParams, *, page: int) -> str:
        query_terms = " ".join(params.search_terms) if params.search_terms else params.extra.get(
            "query", "developer"
        )
        query: dict[str, str | int] = {
            "query": str(query_terms),
            "page": page,
            "num_pages": 1,
            "country": params.extra.get("country", "us"),
            "date_posted": _date_posted_param(params.max_days_old),
        }
        if params.remote_only:
            query["work_from_home"] = "true"
        if params.salary_min is not None:
            query["salary_min"] = params.salary_min
        return f"{_jsearch_base_url()}?{urlencode(query)}"

    async def fetch(self, params: FetchParams) -> FetchResult:
        if self.quota is not None and self.quota.remaining(self.source_name) <= 0:
            raise QuotaExceededError("Daily JSearch quota exhausted")

        client = await self._get_client()
        collected_at = self.utc_now()
        reference = collected_at.date()

        all_jobs: list[StandardJob] = []
        filtered_out = 0
        raw_pages: list[dict[str, Any]] = []
        requests_used = 0
        start_page = max(1, params.page)
        end_page = start_page + self.max_pages - 1

        for page in range(start_page, end_page + 1):
            if self.quota is not None and not self.quota.try_consume(self.source_name, 1):
                break

            url = self._build_url(params, page=page)
            try:
                response = await self._get_with_retry(client, url)
            except httpx.HTTPStatusError as exc:
                err = parse_jsearch_error(exc.response)
                logger.error(
                    "jsearch fetch aborted term=%r page=%d status=%s message=%s",
                    " ".join(params.search_terms) if params.search_terms else params.extra.get("query"),
                    page,
                    err.status_code,
                    err.message,
                )
                raise err from exc
            payload = response.json()
            raw_pages.append(payload)
            requests_used += 1

            data = payload.get("data") or payload.get("jobs") or []
            if isinstance(data, dict):
                data = data.get("jobs") or data.get("results") or []
            if not isinstance(data, list):
                data = []

            for record in data:
                if not isinstance(record, dict):
                    continue
                job = _map_jsearch_record(record, collected_at)
                if _passes_safety_net(
                    job,
                    salary_min=params.salary_min,
                    max_days_old=params.max_days_old,
                    remote_only=params.remote_only,
                    reference=reference,
                ):
                    all_jobs.append(job)
                else:
                    filtered_out += 1

            delay = _inter_request_delay_seconds()
            if delay and page < end_page:
                await asyncio.sleep(delay)

        total = None
        if raw_pages:
            total = raw_pages[0].get("total_jobs") or raw_pages[0].get("count")

        return FetchResult(
            jobs=all_jobs,
            source=self.source_name,
            requests_used=requests_used,
            page=start_page,
            total_available=total,
            filtered_out=filtered_out,
            raw_pages=raw_pages,
        )
