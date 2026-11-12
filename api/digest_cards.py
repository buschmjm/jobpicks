"""Helpers to render match cards for digest email (plan §5 contract)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from core.models import Job, RemoteMode, UserJobQueue


def format_salary(job: Job) -> str:
    if job.salary_min is None and job.salary_max is None:
        return "salary not listed"
    lo = job.salary_min
    hi = job.salary_max
    if lo is not None and hi is not None:
        return f"${lo // 1000}–{hi // 1000}k"
    if lo is not None:
        return f"${lo // 1000}k+"
    if hi is not None:
        return f"up to ${hi // 1000}k"
    return "salary not listed"


def format_work_mode(job: Job) -> str:
    mode = job.remote_mode
    mode_value = mode.value if isinstance(mode, RemoteMode) else str(mode)
    location = job.location_text or "Location TBD"
    if mode_value == RemoteMode.REMOTE.value:
        return f"Remote ({job.country or 'US'})"
    if mode_value == RemoteMode.HYBRID.value:
        return f"{location} (hybrid)"
    if mode_value == RemoteMode.ONSITE.value:
        return location
    return location


def format_posted_ago(job: Job, *, now: datetime | None = None) -> str:
    ref = now or datetime.now(UTC)
    posted = job.date_posted
    days = max(0, (ref.date() - job.first_seen.date()).days) if posted is None else max(0, (ref.date() - posted).days)
    if days == 0:
        return "today"
    if days == 1:
        return "1d ago"
    return f"{days}d ago"


@dataclass(frozen=True)
class DigestCard:
    match_score: int
    title: str
    company: str
    salary_display: str
    work_mode_display: str
    posted_ago: str
    source: str
    why_bullets: list[str]
    caution_bullets: list[str]
    source_url: str


def queue_item_to_digest_card(item: UserJobQueue, job: Job, *, now: datetime | None = None) -> DigestCard:
    explain = item.explain or {}
    why = list(explain.get("why_bullets") or explain.get("why") or [])[:4]
    caution = list(explain.get("caution_bullets") or explain.get("caution") or [])[:2]
    score = int(round(float(item.score or 0) * 100)) if item.score is not None else 0
    score = max(0, min(100, score))
    return DigestCard(
        match_score=score,
        title=job.title,
        company=job.company_name,
        salary_display=format_salary(job),
        work_mode_display=format_work_mode(job),
        posted_ago=format_posted_ago(job, now=now),
        source=job.primary_source or "unknown",
        why_bullets=why,
        caution_bullets=caution,
        source_url=job.source_url or "",
    )


def card_to_template_context(card: DigestCard) -> dict[str, Any]:
    return {
        "match_score": card.match_score,
        "title": card.title,
        "company": card.company,
        "salary_display": card.salary_display,
        "work_mode_display": card.work_mode_display,
        "posted_ago": card.posted_ago,
        "source": card.source,
        "why_bullets": card.why_bullets,
        "caution_bullets": card.caution_bullets,
        "source_url": card.source_url,
    }
