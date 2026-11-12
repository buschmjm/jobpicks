"""Greenhouse Job Board API adapter (plan §8, Tier 2)."""

from __future__ import annotations

from datetime import date, datetime
from html import unescape
from typing import Any
from urllib.parse import urlencode

import httpx
from core.apply.ats_detect import enrich_standard_job_apply

from ingest.base import FetchParams, FetchResult, SourceAdapter
from ingest.country import resolve_job_country
from ingest.html_utils import html_to_plain_text
from ingest.quota import QuotaTracker
from ingest.rate_limit import DEFAULT_USER_AGENT, HostRateLimiter
from ingest.schema import EmploymentType, StandardJob, WorkArrangement

GREENHOUSE_HOST = "boards-api.greenhouse.io"
GREENHOUSE_BASE = f"https://{GREENHOUSE_HOST}/v1/boards"


def _parse_date(value: str | None, fallback: datetime) -> date:
    if not value:
        return fallback.date()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return fallback.date()


def _infer_remote(location: str, description: str) -> bool | None:
    text = f"{location} {description}".lower()
    if "remote" in text or "work from home" in text or "wfh" in text:
        return True
    if "hybrid" in text:
        return None
    return None


def _map_work_arrangement(location: str, description: str, remote: bool | None) -> WorkArrangement:
    text = f"{location} {description}".lower()
    if "hybrid" in text:
        return WorkArrangement.HYBRID
    if remote is True:
        return WorkArrangement.REMOTE
    if remote is False:
        return WorkArrangement.ONSITE
    return WorkArrangement.UNKNOWN


def _map_greenhouse_record(
    record: dict[str, Any],
    *,
    company_name: str,
    collected_at: datetime,
) -> StandardJob:
    location_obj = record.get("location") or {}
    location = location_obj.get("name") if isinstance(location_obj, dict) else str(location_obj)
    location = (location or "Unknown").strip()

    content_html = unescape((record.get("content") or "").strip())
    description = content_html or record.get("title") or "No description provided."
    plain_text = html_to_plain_text(content_html) if content_html else description

    remote = _infer_remote(location, plain_text)

    source_url = (record.get("absolute_url") or "").strip()
    apply_url, ats_type, ats_metadata = enrich_standard_job_apply(source_url=source_url)

    return StandardJob(
        title=record.get("title") or "Untitled",
        company=company_name,
        location=location,
        remote=remote,
        latitude=None,
        longitude=None,
        employment_type=EmploymentType.UNKNOWN,
        salary=None,
        date_posted=_parse_date(record.get("updated_at"), collected_at),
        description=description,
        requirements=None,
        source="greenhouse",
        source_url=source_url,
        collected_timestamp=collected_at,
        apply_url=apply_url,
        ats_type=ats_type,
        ats_metadata=ats_metadata,
        source_id=str(record.get("id")) if record.get("id") is not None else None,
        country=resolve_job_country(country=None, location=location),
        work_arrangement=_map_work_arrangement(location, plain_text, remote),
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


class GreenhouseAdapter(SourceAdapter):
    """Greenhouse Job Board API — public JSON per company board token."""

    source_name = "greenhouse"

    def __init__(
        self,
        *,
        board_token: str | None = None,
        company_name: str | None = None,
        client: httpx.AsyncClient | None = None,
        quota: QuotaTracker | None = None,
        rate_limiter: HostRateLimiter | None = None,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        super().__init__(client=client, quota=quota)
        self.board_token = board_token
        self.company_name = company_name
        self.rate_limiter = rate_limiter or HostRateLimiter()
        self.user_agent = user_agent

    def _resolve_board_token(self, params: FetchParams) -> str:
        token = params.extra.get("board_token") or self.board_token
        if not token:
            msg = "board_token must be set on adapter or FetchParams.extra"
            raise ValueError(msg)
        return str(token)

    def _resolve_company_name(self, params: FetchParams) -> str:
        name = params.extra.get("company_name") or self.company_name
        if not name:
            msg = "company_name must be set on adapter or FetchParams.extra"
            raise ValueError(msg)
        return str(name)

    def _build_url(self, board_token: str, params: FetchParams) -> str:
        query: dict[str, str] = {"content": "true"}
        if params.extra.get("department_id"):
            query["department_id"] = str(params.extra["department_id"])
        if params.extra.get("office_id"):
            query["office_id"] = str(params.extra["office_id"])
        encoded = urlencode(query)
        return f"{GREENHOUSE_BASE}/{board_token}/jobs?{encoded}"

    async def fetch(self, params: FetchParams) -> FetchResult:
        self._reserve_quota(1)
        board_token = self._resolve_board_token(params)
        company_name = self._resolve_company_name(params)
        client = await self._get_client()

        await self.rate_limiter.wait(GREENHOUSE_HOST)
        url = self._build_url(board_token, params)
        response = await client.get(url, headers={"User-Agent": self.user_agent})
        response.raise_for_status()
        payload = response.json()

        collected_at = self.utc_now()
        reference = collected_at.date()
        jobs: list[StandardJob] = []
        filtered_out = 0

        for record in payload.get("jobs") or []:
            job = _map_greenhouse_record(record, company_name=company_name, collected_at=collected_at)
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

        meta = payload.get("meta") or {}
        return FetchResult(
            jobs=jobs,
            source=self.source_name,
            requests_used=1,
            page=1,
            total_available=meta.get("total"),
            filtered_out=filtered_out,
            raw_pages=[payload],
        )
