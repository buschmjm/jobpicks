"""Hard constraint filtering — jobs that fail must never be scored or recommended."""

from __future__ import annotations

import math

from ingest.country import is_us_job_record

from core.types import HardConstraints, JobFeatures, RemoteMode, RemoteOpenness


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_miles = 3958.8
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * radius_miles * math.asin(min(1.0, math.sqrt(a)))


def _job_salary_floor(job: JobFeatures) -> float | None:
    if job.salary_min is not None:
        return job.salary_min
    return job.salary_max


def _remote_allowed(job: JobFeatures, allowed: frozenset[RemoteMode]) -> bool:
    if job.remote_mode == RemoteMode.UNKNOWN:
        return RemoteMode.UNKNOWN in allowed or RemoteMode.ONSITE in allowed
    return job.remote_mode in allowed


def _passes_remote_openness(job: JobFeatures, openness: RemoteOpenness) -> bool:
    if job.remote_mode == RemoteMode.REMOTE:
        return openness in {RemoteOpenness.OPEN_TO_REMOTE, RemoteOpenness.REMOTE_ONLY}
    return openness != RemoteOpenness.REMOTE_ONLY


def _passes_commute(job: JobFeatures, constraints: HardConstraints) -> bool:
    if constraints.remote_openness == RemoteOpenness.REMOTE_ONLY:
        return False
    if job.remote_mode == RemoteMode.REMOTE:
        return True
    if job.remote_mode not in {RemoteMode.ONSITE, RemoteMode.HYBRID, RemoteMode.UNKNOWN}:
        return True

    if constraints.home_lat is None or constraints.home_lon is None:
        return False
    if constraints.max_commute_minutes is None:
        return False
    if job.commute_minutes is None:
        return False
    return job.commute_minutes <= constraints.max_commute_minutes


def passes_hard_constraints(job: JobFeatures, constraints: HardConstraints) -> bool:
    """Return True only if the job satisfies every hard constraint."""
    if job.is_closed:
        return False

    if job.company_id in constraints.blocked_companies or job.company_name in constraints.blocked_companies:
        return False

    if job.industry and job.industry in constraints.blocked_industries:
        return False

    if constraints.min_salary is not None:
        salary = _job_salary_floor(job)
        if salary is not None and salary < constraints.min_salary:
            return False

    if not _remote_allowed(job, constraints.allowed_remote_modes):
        return False

    if not _passes_remote_openness(job, constraints.remote_openness):
        return False

    if job.remote_mode != RemoteMode.REMOTE and constraints.remote_openness != RemoteOpenness.REMOTE_ONLY:
        if job.remote_mode == RemoteMode.UNKNOWN:
            return True
        if not _passes_commute(job, constraints):
            return False

    # Legacy miles-based fallback when commute minutes were not enriched
    if (
        job.commute_minutes is None
        and job.remote_mode in {RemoteMode.ONSITE, RemoteMode.HYBRID}
        and constraints.max_commute_radius_miles is not None
        and constraints.home_lat is not None
        and constraints.home_lon is not None
        and job.lat is not None
        and job.lon is not None
    ):
        distance = _haversine_miles(constraints.home_lat, constraints.home_lon, job.lat, job.lon)
        if distance > constraints.max_commute_radius_miles:
            return False

    if constraints.requires_work_authorization and job.requires_work_authorization:
        if not constraints.user_has_work_authorization:
            return False

    return is_us_job_record(
        country=job.country,
        location=job.location_text,
        source=job.facet_values.get("primary_source"),
    )


def filter_hard_constraints(
    jobs: list[JobFeatures],
    constraints: HardConstraints,
) -> list[JobFeatures]:
    """Return only jobs that pass hard constraints."""
    return [job for job in jobs if passes_hard_constraints(job, constraints)]
