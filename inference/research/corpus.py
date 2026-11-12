"""Search JobDeck open-job corpus for localized market evidence."""

from __future__ import annotations

import logging
import re
from typing import Any

from core.job_retention import open_corpus_filter
from core.models import Job, JobStatus
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_TOKEN = re.compile(r"[A-Za-z0-9+#.]{2,}")


def search_corpus(
    session: Session,
    query: str,
    *,
    location_hint: str | None = None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Return compact open-job rows matching title/location/skills tokens."""
    tokens = _TOKEN.findall(query or "")[:6]
    if not tokens and location_hint:
        tokens = _TOKEN.findall(location_hint)[:3]
    if not tokens:
        return []

    clauses = []
    for tok in tokens:
        pattern = f"%{tok}%"
        clauses.append(Job.title.ilike(pattern))
        clauses.append(Job.normalized_title.ilike(pattern))
        clauses.append(Job.location_text.ilike(pattern))
        clauses.append(Job.company_name.ilike(pattern))

    loc = (location_hint or "").strip()
    if loc:
        clauses.append(Job.location_text.ilike(f"%{loc}%"))
        clauses.append(Job.city.ilike(f"%{loc}%"))
        clauses.append(Job.state.ilike(f"%{loc}%"))

    stmt = (
        select(Job)
        .where(Job.status == JobStatus.OPEN.value)
        .where(open_corpus_filter())
        .where(or_(*clauses))
        .order_by(Job.last_seen.desc())
        .limit(max(1, min(limit, 12)))
    )
    try:
        rows = session.scalars(stmt).all()
    except Exception as exc:
        logger.warning("corpus_search failed: %s", exc)
        return []

    out: list[dict[str, Any]] = []
    for job in rows:
        salary = _format_salary(job)
        out.append(
            {
                "title": job.title,
                "company": job.company_name,
                "location": job.location_text or "",
                "salary": salary,
                "source_url": (job.source_url or "")[:2048],
                "publisher": "jobdeck-corpus",
            }
        )
    return out


def _format_salary(job: Job) -> str:
    if job.salary_min is None and job.salary_max is None:
        return ""
    currency = job.salary_currency or "USD"
    period = job.salary_period or "year"
    if job.salary_min is not None and job.salary_max is not None:
        return f"{currency} {job.salary_min}-{job.salary_max}/{period}"
    value = job.salary_min if job.salary_min is not None else job.salary_max
    return f"{currency} {value}/{period}"
