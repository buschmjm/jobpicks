"""Attainability scoring for deck vs search (Workstream F2)."""

from __future__ import annotations

import logging
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.orm import Session

from core.types import JobFeatures, UserProfile

logger = logging.getLogger(__name__)

ATTAINABILITY_DECK_FLOOR = 0.15
DECK_RANK_EXPONENT = 1.5  # LOCKED


def level_factor(delta: int) -> float:
    if delta <= 0:
        return 1.0
    if delta == 1:
        return 0.75
    if delta == 2:
        return 0.35
    return 0.10


def salary_factor(ratio: float) -> float:
    if ratio <= 1.25:
        return 1.0
    if ratio <= 1.60:
        return 1.0 - (ratio - 1.25) * (0.4 / 0.35)
    if ratio <= 2.00:
        return 0.6 - (ratio - 1.60) * (0.35 / 0.40)
    return 0.10


def skills_factor(profile_skills: frozenset[str], job_skills: frozenset[str]) -> float:
    if not job_skills:
        return 1.0
    overlap = profile_skills & job_skills
    return len(overlap) / len(job_skills)


def job_salary_midpoint(job: JobFeatures) -> float | None:
    if job.salary_min is not None and job.salary_max is not None:
        return (job.salary_min + job.salary_max) / 2.0
    if job.salary_min is not None:
        return float(job.salary_min)
    if job.salary_max is not None:
        return float(job.salary_max)
    return None


@lru_cache(maxsize=16)
def _cached_median_salary_for_level(level: int) -> float:
    """Process-local fallback when DB session is unavailable."""
    defaults = {
        0: 45_000,
        1: 70_000,
        2: 95_000,
        3: 125_000,
        4: 155_000,
        5: 175_000,
        6: 210_000,
        7: 275_000,
        8: 400_000,
    }
    return float(defaults.get(level, defaults[2]))


def median_salary_midpoint_for_level(session: Session | None, level: int) -> float:
    if session is None:
        return _cached_median_salary_for_level(level)
    row = session.execute(
        text(
            """
            SELECT percentile_cont(0.5) WITHIN GROUP (
                ORDER BY COALESCE(
                    (salary_min + salary_max)::float / 2.0,
                    salary_min::float,
                    salary_max::float
                )
            ) AS median_mid
            FROM jobs
            WHERE status = 'open'
              AND seniority_int = :level
              AND (salary_min IS NOT NULL OR salary_max IS NOT NULL)
            """
        ),
        {"level": level},
    ).mappings().first()
    median = row["median_mid"] if row else None
    if median is None:
        return _cached_median_salary_for_level(level)
    return float(median)


def salary_reference(profile: UserProfile, session: Session | None = None) -> float:
    floor = profile.effective_salary_floor or profile.target_salary
    if floor and floor > 0:
        return float(floor)
    return median_salary_midpoint_for_level(session, profile.seniority_level)


def attainability(
    profile: UserProfile,
    job: JobFeatures,
    *,
    session: Session | None = None,
) -> float:
    """attainability(user, job) ∈ [0,1] — computed at queue-build/search time."""
    delta = job.seniority_level - profile.seniority_level
    level = level_factor(delta)
    skills = skills_factor(profile.skills, job.skills)

    job_mid = job_salary_midpoint(job)
    if job_mid is None:
        salary = 1.0
    else:
        ref = salary_reference(profile, session)
        ratio = job_mid / ref if ref > 0 else 1.0
        salary = salary_factor(ratio)

    return max(0.0, min(1.0, level * salary * skills))


def deck_rank_score(match_score: float, attainability_score: float) -> float:
    return float(match_score * (attainability_score**DECK_RANK_EXPONENT))
