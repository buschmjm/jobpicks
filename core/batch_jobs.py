"""Nightly batch: LLM job normalization and embedding generation."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from inference.client import InferenceUnavailableError
from inference.embeddings import EmbeddingClient
from inference.extraction import ExtractionError, extract_job_fields
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from core.job_skill_extract import heuristic_normalize_text
from core.models import Job, JobStatus, RemoteMode
from core.seniority import derive_seniority_from_title, seniority_to_int

logger = logging.getLogger(__name__)

# Sources with pre-extracted structure — skip LLM (plan §9).
_DETERMINISTIC_SOURCES = frozenset({"jsearch"})

_DEFAULT_NORMALIZE_BATCH = 50
_DEFAULT_EMBED_BATCH = 200


def _job_document_text(job: Job) -> str:
    parts = [job.title, job.company_name]
    if job.description:
        parts.append(job.description)
    if job.requirements:
        parts.append(job.requirements)
    return "\n\n".join(parts)[:8000]


def _is_normalized(job: Job) -> bool:
    raw = job.raw or {}
    return bool(raw.get("llm_normalized") or raw.get("heuristic_normalized"))


def _needs_llm_normalize(job: Job) -> bool:
    source = (job.primary_source or "").lower()
    if source in _DETERMINISTIC_SOURCES:
        return False
    if _is_normalized(job):
        return False
    return job.skills is None or job.seniority_level is None


def _apply_normalized_fields(
    job: Job,
    data: dict[str, object],
    *,
    source: str = "llm",
) -> None:
    skills = data.get("required_skills")
    if isinstance(skills, list):
        job.skills = [str(s).lower() for s in skills if str(s).strip()]
    seniority = data.get("seniority_level")
    if seniority:
        job.seniority_level = str(seniority)
        job.seniority_int = seniority_to_int(str(seniority))
    elif job.title:
        job.seniority_int = derive_seniority_from_title(job.title)
    salary_min = data.get("salary_min")
    if isinstance(salary_min, int) and job.salary_min is None:
        job.salary_min = salary_min
    salary_max = data.get("salary_max")
    if isinstance(salary_max, int) and job.salary_max is None:
        job.salary_max = salary_max
    arrangement = str(data.get("work_arrangement") or "unknown").lower()
    if arrangement == "remote":
        job.remote_mode = RemoteMode.REMOTE
    elif arrangement == "hybrid":
        job.remote_mode = RemoteMode.HYBRID
    elif arrangement == "onsite":
        job.remote_mode = RemoteMode.ONSITE
    raw = dict(job.raw or {})
    raw["normalized_at"] = datetime.now(UTC).isoformat()
    if source == "heuristic":
        raw["heuristic_normalized"] = True
    else:
        raw["llm_normalized"] = True
    job.raw = raw


def _apply_heuristic_fields(job: Job) -> bool:
    data = heuristic_normalize_text(job.title, _job_document_text(job))
    skills = data.get("required_skills")
    has_skills = isinstance(skills, list) and len(skills) > 0
    has_seniority = bool(data.get("seniority_level"))
    has_arrangement = bool(data.get("work_arrangement"))
    if not has_skills and not has_seniority and not has_arrangement:
        return False
    _apply_normalized_fields(job, data, source="heuristic")
    if job.seniority_int is None and job.title:
        job.seniority_int = derive_seniority_from_title(job.title)
    return True


def normalize_jobs_batch(session: Session, *, batch_size: int = _DEFAULT_NORMALIZE_BATCH) -> dict[str, int]:
    """LLM-normalize Adzuna/Remotive/ATS jobs missing structured fields."""
    rows = session.scalars(
        select(Job)
        .where(Job.status == JobStatus.OPEN.value)
        .where(
            or_(
                Job.skills.is_(None),
                Job.seniority_level.is_(None),
            )
        )
        .order_by(Job.first_seen.desc())
        .limit(batch_size * 3)
    ).all()

    stats = {
        "candidates": len(rows),
        "normalized": 0,
        "heuristic": 0,
        "skipped": 0,
        "errors": 0,
    }
    processed = 0

    for job in rows:
        if processed >= batch_size:
            break
        if not _needs_llm_normalize(job):
            stats["skipped"] += 1
            continue
        processed += 1
        try:
            data = extract_job_fields(_job_document_text(job))
            _apply_normalized_fields(job, data, source="llm")
            stats["normalized"] += 1
        except (ExtractionError, InferenceUnavailableError) as exc:
            logger.warning("normalize failed job=%s: %s", job.id, exc)
            if _apply_heuristic_fields(job):
                stats["heuristic"] += 1
            else:
                stats["errors"] += 1

    session.flush()
    logger.info("normalize batch stats=%s", stats)
    return stats


def embed_jobs_batch(session: Session, *, batch_size: int = _DEFAULT_EMBED_BATCH) -> dict[str, int]:
    """Generate missing job embeddings via nomic-embed-text."""
    rows = session.scalars(
        select(Job)
        .where(Job.status == JobStatus.OPEN.value)
        .where(Job.embedding.is_(None))
        .order_by(Job.first_seen.desc())
        .limit(batch_size)
    ).all()

    if not rows:
        return {"embedded": 0}

    client = EmbeddingClient()
    texts = [_job_document_text(job) for job in rows]
    try:
        vectors = client.embed_many(texts)
    except InferenceUnavailableError as exc:
        logger.warning("embed batch skipped: %s", exc)
        return {"embedded": 0, "errors": len(rows)}

    for job, vector in zip(rows, vectors, strict=True):
        job.embedding = vector

    session.flush()
    logger.info("embed batch embedded=%d", len(rows))
    return {"embedded": len(rows)}


def corpus_skill_coverage(session: Session) -> float:
    """Share of open corpus jobs with at least one extracted skill."""
    from sqlalchemy import text

    row = session.execute(
        text(
            """
            SELECT
              COUNT(*)::float AS total,
              COUNT(*) FILTER (
                WHERE skills IS NOT NULL
                  AND jsonb_typeof(skills) = 'array'
                  AND jsonb_array_length(skills) > 0
              )::float AS with_skills
            FROM jobs
            WHERE status = 'open'
            """
        )
    ).mappings().first()
    if not row or not row["total"]:
        return 0.0
    return float(row["with_skills"]) / float(row["total"])
