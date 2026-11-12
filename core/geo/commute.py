"""Commute-time resolution with estimate-first routing and optional Mapbox refinement."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.constraints import _haversine_miles
from core.geo.routing import (
    EstimateRoutingProvider,
    MapboxMatrixProvider,
    estimate_drive_minutes,
    geohash5,
    haversine_prefilter_miles,
    select_routing_provider,
)
from core.geo.usage import can_spend_matrix, record_matrix_elements
from core.models import RouteCache
from core.types import HardConstraints, JobFeatures, RemoteMode

_MATRIX_BATCH_LIMIT = 24


class CommuteResolver:
    def __init__(self, session: Session, constraints: HardConstraints) -> None:
        self._session = session
        self._constraints = constraints
        self._provider = select_routing_provider()
        self._estimate = EstimateRoutingProvider()
        self._cache_keys_written: set[tuple[str, str]] = set()

    def _needs_commute(self, job: JobFeatures) -> bool:
        if self._constraints.remote_openness == "remote_only":
            return False
        if job.remote_mode == RemoteMode.REMOTE:
            return False
        if self._constraints.home_lat is None or self._constraints.home_lon is None:
            return False
        if self._constraints.max_commute_minutes is None:
            return False
        return job.remote_mode in {
            RemoteMode.ONSITE,
            RemoteMode.HYBRID,
            RemoteMode.UNKNOWN,
        }

    def _read_route_cache(self, dest_lat: float, dest_lon: float) -> int | None:
        if self._constraints.home_lat is None or self._constraints.home_lon is None:
            return None
        origin = geohash5(self._constraints.home_lat, self._constraints.home_lon)
        dest = geohash5(dest_lat, dest_lon)
        row = self._session.scalar(
            select(RouteCache).where(
                RouteCache.origin_geohash == origin,
                RouteCache.dest_geohash == dest,
            )
        )
        return row.drive_minutes if row is not None else None

    def _write_route_cache(self, dest_lat: float, dest_lon: float, minutes: int, source: str) -> None:
        if self._constraints.home_lat is None or self._constraints.home_lon is None:
            return
        origin = geohash5(self._constraints.home_lat, self._constraints.home_lon)
        dest = geohash5(dest_lat, dest_lon)
        cache_key = (origin, dest)
        if cache_key in self._cache_keys_written:
            return
        for pending in self._session.new:
            if (
                isinstance(pending, RouteCache)
                and pending.origin_geohash == origin
                and pending.dest_geohash == dest
            ):
                pending.drive_minutes = minutes
                pending.source = source
                pending.computed_at = datetime.now(tz=UTC)
                self._cache_keys_written.add(cache_key)
                return
        row = self._session.scalar(
            select(RouteCache).where(
                RouteCache.origin_geohash == origin,
                RouteCache.dest_geohash == dest,
            )
        )
        if row is None:
            row = RouteCache(
                origin_geohash=origin,
                dest_geohash=dest,
                drive_minutes=minutes,
                source=source,
            )
            self._session.add(row)
        else:
            row.drive_minutes = minutes
            row.source = source
        row.computed_at = datetime.now(tz=UTC)
        self._cache_keys_written.add(cache_key)

    def resolve_one(self, job: JobFeatures) -> int | None:
        if not self._needs_commute(job):
            return None
        if job.lat is None or job.lon is None:
            return None
        assert self._constraints.home_lat is not None
        assert self._constraints.home_lon is not None

        cached = self._read_route_cache(job.lat, job.lon)
        if cached is not None:
            return cached

        minutes = estimate_drive_minutes(
            self._constraints.home_lat,
            self._constraints.home_lon,
            job.lat,
            job.lon,
        )
        self._write_route_cache(job.lat, job.lon, minutes, "estimate")
        return minutes

    def resolve_batch(self, jobs: list[JobFeatures]) -> dict[str, int]:
        if self._constraints.home_lat is None or self._constraints.home_lon is None:
            return {}
        if self._constraints.max_commute_minutes is None:
            return {}

        max_miles = haversine_prefilter_miles(self._constraints.max_commute_minutes)
        pending: list[JobFeatures] = []
        resolved: dict[str, int] = {}

        for job in jobs:
            if not self._needs_commute(job) or job.lat is None or job.lon is None:
                continue
            cached = self._read_route_cache(job.lat, job.lon)
            if cached is not None:
                resolved[job.job_id] = cached
                continue
            miles = _haversine_miles(
                self._constraints.home_lat,
                self._constraints.home_lon,
                job.lat,
                job.lon,
            )
            if miles <= max_miles:
                pending.append(job)

        if not pending:
            return resolved

        # Estimate all pending first (free)
        for job in pending:
            assert job.lat is not None and job.lon is not None
            minutes = estimate_drive_minutes(
                self._constraints.home_lat,
                self._constraints.home_lon,
                job.lat,
                job.lon,
            )
            resolved[job.job_id] = minutes
            self._write_route_cache(job.lat, job.lon, minutes, "estimate")

        # Optional Mapbox refinement for a small batch under budget
        if (
            isinstance(self._provider, MapboxMatrixProvider)
            and can_spend_matrix(self._session, elements=len(pending[:_MATRIX_BATCH_LIMIT]))
        ):
            batch = pending[:_MATRIX_BATCH_LIMIT]
            destinations = [(job.job_id, job.lat, job.lon) for job in batch if job.lat and job.lon]
            matrix = self._provider.drive_minutes_batch(
                self._constraints.home_lat,
                self._constraints.home_lon,
                destinations,
            )
            if matrix:
                record_matrix_elements(self._session, elements=len(matrix))
                for job_id, minutes in matrix.items():
                    resolved[job_id] = minutes
                    job = next(j for j in batch if j.job_id == job_id)
                    if job.lat is not None and job.lon is not None:
                        self._write_route_cache(job.lat, job.lon, minutes, "mapbox")

        return resolved


def enrich_commute_minutes(
    session: Session,
    constraints: HardConstraints,
    jobs: list[JobFeatures],
) -> list[JobFeatures]:
    resolver = CommuteResolver(session, constraints)
    minutes_by_id = resolver.resolve_batch(jobs)
    enriched: list[JobFeatures] = []
    for job in jobs:
        minutes = minutes_by_id.get(job.job_id)
        if minutes is None:
            minutes = resolver.resolve_one(job)
        enriched.append(replace(job, commute_minutes=minutes))
    return enriched
