"""Geocoding with local centroids first and optional Mapbox Temporary API."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

import httpx
from api.settings import settings
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.geo.centroids import lookup_city_state, lookup_location_text
from core.geo.usage import can_spend_geocode, record_geocode_call
from core.models import Job, LocationGeocodeCache

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GeocodeResult:
    lat: float
    lon: float
    formatted_name: str
    source: str


class GeocodeProvider(Protocol):
    def geocode(self, query: str) -> GeocodeResult | None: ...


def normalize_location_key(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text.strip().lower())
    return cleaned[:512]


def geocode_from_centroids(*, city: str | None, state: str | None, location: str | None) -> GeocodeResult | None:
    if city and state:
        coords = lookup_city_state(city, state)
        if coords is not None:
            label = f"{city}, {state}"
            return GeocodeResult(lat=coords[0], lon=coords[1], formatted_name=label, source="centroid")
    if location:
        coords = lookup_location_text(location)
        if coords is not None:
            return GeocodeResult(
                lat=coords[0],
                lon=coords[1],
                formatted_name=location.strip(),
                source="centroid",
            )
    return None


class MapboxGeocodeProvider:
    def geocode(self, query: str) -> GeocodeResult | None:
        token = settings.mapbox_access_token
        if not token:
            return None
        url = "https://api.mapbox.com/search/geocode/v6/forward"
        params: dict[str, str | int] = {
            "q": query,
            "access_token": token,
            "country": "us",
            "limit": 1,
        }
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(url, params=params)
                response.raise_for_status()
                payload = response.json()
        except Exception:
            logger.exception("mapbox geocode failed for %r", query)
            return None

        features = payload.get("features") or []
        if not features:
            return None
        feature = features[0]
        coords = feature.get("geometry", {}).get("coordinates") or []
        if len(coords) < 2:
            return None
        lon, lat = float(coords[0]), float(coords[1])
        name = feature.get("properties", {}).get("full_address") or query
        return GeocodeResult(lat=lat, lon=lon, formatted_name=name, source="mapbox")


def _read_cache(session: Session, key: str) -> GeocodeResult | None:
    row = session.scalar(select(LocationGeocodeCache).where(LocationGeocodeCache.normalized_key == key))
    if row is None:
        return None
    return GeocodeResult(
        lat=row.lat,
        lon=row.lon,
        formatted_name=row.formatted_name or key,
        source=row.source or "cache",
    )


def _write_cache(session: Session, key: str, result: GeocodeResult) -> None:
    row = session.scalar(select(LocationGeocodeCache).where(LocationGeocodeCache.normalized_key == key))
    if row is None:
        row = LocationGeocodeCache(
            normalized_key=key,
            lat=result.lat,
            lon=result.lon,
            formatted_name=result.formatted_name,
            source=result.source,
        )
        session.add(row)
    else:
        row.lat = result.lat
        row.lon = result.lon
        row.formatted_name = result.formatted_name
        row.source = result.source
    row.updated_at = datetime.now(tz=UTC)


def geocode_us_address(
    session: Session,
    query: str,
    *,
    city: str | None = None,
    state: str | None = None,
    allow_mapbox: bool = True,
) -> GeocodeResult | None:
    """Resolve a US address/location to coordinates."""
    key = normalize_location_key(query)
    cached = _read_cache(session, key)
    if cached is not None:
        return cached

    local = geocode_from_centroids(city=city, state=state, location=query)
    if local is not None:
        _write_cache(session, key, local)
        return local

    if allow_mapbox and can_spend_geocode(session):
        provider = MapboxGeocodeProvider()
        remote = provider.geocode(query)
        if remote is not None:
            record_geocode_call(session, count=1)
            _write_cache(session, key, remote)
            return remote

    return None


def resolve_job_coordinates(session: Session, job: Job) -> GeocodeResult | None:
    if job.latitude is not None and job.longitude is not None:
        return GeocodeResult(
            lat=job.latitude,
            lon=job.longitude,
            formatted_name=job.location_text or f"{job.city}, {job.state}",
            source="job",
        )
    query = ", ".join(
        part
        for part in [job.city, job.state, "US"]
        if part
    )
    if not query and job.location_text:
        query = job.location_text
    if not query:
        return None
    result = geocode_us_address(
        session,
        query,
        city=job.city,
        state=job.state,
        allow_mapbox=True,
    )
    if result is not None:
        job.latitude = result.lat
        job.longitude = result.lon
        job.geocoded_at = datetime.now(tz=UTC)
    return result
