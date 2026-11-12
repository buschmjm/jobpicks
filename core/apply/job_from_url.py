"""Import a single job posting from a direct ATS apply URL."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any

import httpx
from ingest.adapters.greenhouse import _map_greenhouse_record
from ingest.adapters.lever import _map_lever_record
from ingest.pipeline import canonical_hash
from ingest.schema import StandardJob

from core.apply.ats_detect import detect_ats, enrich_standard_job_apply

logger = logging.getLogger(__name__)

_GH_API = "https://boards-api.greenhouse.io/v1/boards"
_LEVER_API = "https://api.lever.co/v0/postings"


class JobFromUrlError(ValueError):
    """User-facing import failure."""


def _company_from_metadata(ats_type: str, metadata: dict[str, Any]) -> str:
    if ats_type == "greenhouse":
        return str(metadata.get("board_token") or "Unknown").replace("-", " ").title()
    if ats_type == "lever":
        return str(metadata.get("site_slug") or "Unknown").replace("-", " ").title()
    if ats_type == "ashby":
        return str(metadata.get("org_slug") or "Unknown").replace("-", " ").title()
    return "Unknown"


def _fetch_greenhouse_job(*, board_token: str, posting_id: str) -> dict[str, Any]:
    url = f"{_GH_API}/{board_token}/jobs/{posting_id}"
    response = httpx.get(url, params={"content": "true"}, timeout=15.0)
    if response.status_code == 404:
        raise JobFromUrlError("Greenhouse posting not found or no longer open")
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise JobFromUrlError("Unexpected Greenhouse response")
    return payload


def _fetch_lever_job(*, posting_id: str) -> dict[str, Any]:
    url = f"{_LEVER_API}/{posting_id}"
    response = httpx.get(url, params={"mode": "json"}, timeout=15.0)
    if response.status_code == 404:
        raise JobFromUrlError("Lever posting not found or no longer open")
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise JobFromUrlError("Unexpected Lever response")
    return payload


def _fallback_standard_job(*, url: str, ats_type: str | None, metadata: dict[str, Any]) -> StandardJob:
    apply_url, detected_type, ats_metadata = enrich_standard_job_apply(
        source_url=url,
        apply_url=url,
        ats_type=ats_type,
        ats_metadata=metadata,
    )
    title = "Imported role"
    if detected_type == "greenhouse" and metadata.get("posting_id"):
        title = f"Greenhouse posting {metadata['posting_id']}"
    collected = datetime.now(tz=UTC)
    job = StandardJob(
        title=title,
        company=_company_from_metadata(detected_type or "unknown", ats_metadata),
        location="Unknown",
        remote=None,
        description="Imported from apply URL. Open the posting to review full details.",
        source="user_url",
        source_url=url,
        collected_timestamp=collected,
        apply_url=apply_url,
        ats_type=detected_type,
        ats_metadata=ats_metadata,
        date_posted=collected.date(),
    )
    return job.model_copy(
        update={"canonical_hash": canonical_hash(job.title, job.company, job.location, job.description)}
    )


def standard_job_from_url(url: str) -> StandardJob:
    """Build a StandardJob from a public ATS apply URL."""
    cleaned = (url or "").strip()
    if not cleaned:
        raise JobFromUrlError("URL is required")
    if not re.match(r"^https?://", cleaned, re.I):
        raise JobFromUrlError("URL must start with http:// or https://")

    ats_type, metadata = detect_ats(cleaned)
    collected = datetime.now(tz=UTC)

    if ats_type == "greenhouse":
        board_token = str(metadata.get("board_token") or "").strip()
        posting_id = str(metadata.get("posting_id") or "").strip()
        if not board_token or not posting_id:
            raise JobFromUrlError("Could not parse Greenhouse board token and posting id from URL")
        record = _fetch_greenhouse_job(board_token=board_token, posting_id=posting_id)
        company_name = (
            str(record.get("company_name") or "").strip()
            or _company_from_metadata("greenhouse", metadata)
        )
        job = _map_greenhouse_record(record, company_name=company_name, collected_at=collected)
        apply_url, final_type, ats_metadata = enrich_standard_job_apply(
            source_url=cleaned,
            apply_url=job.source_url,
            ats_type="greenhouse",
            ats_metadata=metadata,
        )
        return job.model_copy(
            update={
                "source": "user_url",
                "source_url": cleaned,
                "apply_url": apply_url,
                "ats_type": final_type,
                "ats_metadata": ats_metadata,
                "canonical_hash": canonical_hash(job.title, job.company, job.location, job.description),
            }
        )

    if ats_type == "lever":
        posting_id = str(metadata.get("posting_id") or "").strip()
        if not posting_id:
            raise JobFromUrlError("Could not parse Lever posting id from URL")
        record = _fetch_lever_job(posting_id=posting_id)
        company_name = _company_from_metadata("lever", metadata)
        job = _map_lever_record(record, company_name=company_name, collected_at=collected)
        apply_url, final_type, ats_metadata = enrich_standard_job_apply(
            source_url=cleaned,
            apply_url=job.source_url,
            ats_type="lever",
            ats_metadata=metadata,
        )
        return job.model_copy(
            update={
                "source": "user_url",
                "source_url": cleaned,
                "apply_url": apply_url,
                "ats_type": final_type,
                "ats_metadata": ats_metadata,
                "canonical_hash": canonical_hash(job.title, job.company, job.location, job.description),
            }
        )

    logger.info("job_from_url fallback ats_type=%s url=%s", ats_type, cleaned)
    return _fallback_standard_job(url=cleaned, ats_type=ats_type, metadata=metadata)
