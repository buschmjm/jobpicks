"""Drive-time estimation and optional Mapbox Matrix routing."""

from __future__ import annotations

import logging
from typing import Protocol

import httpx
from api.settings import settings

from core.constraints import _haversine_miles

logger = logging.getLogger(__name__)

ROAD_FACTOR = 1.25
AVG_SPEED_MPH = 45.0


def geohash5(lat: float, lon: float) -> str:
    """Round coordinates to ~1.1km grid for route cache keys."""
    return f"{round(lat, 2):.2f},{round(lon, 2):.2f}"


def estimate_drive_minutes(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
) -> int:
    miles = _haversine_miles(origin_lat, origin_lon, dest_lat, dest_lon) * ROAD_FACTOR
    minutes = (miles / AVG_SPEED_MPH) * 60.0
    return max(1, int(round(minutes)))


def haversine_prefilter_miles(max_commute_minutes: int) -> float:
    """Upper-bound straight-line miles before calling a routing API."""
    max_road_miles = (max_commute_minutes / 60.0) * AVG_SPEED_MPH
    return max_road_miles / ROAD_FACTOR


class RoutingProvider(Protocol):
    def drive_minutes_batch(
        self,
        origin_lat: float,
        origin_lon: float,
        destinations: list[tuple[str, float, float]],
    ) -> dict[str, int]: ...


class EstimateRoutingProvider:
    def drive_minutes_batch(
        self,
        origin_lat: float,
        origin_lon: float,
        destinations: list[tuple[str, float, float]],
    ) -> dict[str, int]:
        out: dict[str, int] = {}
        for key, lat, lon in destinations:
            out[key] = estimate_drive_minutes(origin_lat, origin_lon, lat, lon)
        return out


class MapboxMatrixProvider:
    def drive_minutes_batch(
        self,
        origin_lat: float,
        origin_lon: float,
        destinations: list[tuple[str, float, float]],
    ) -> dict[str, int]:
        token = settings.mapbox_access_token
        if not token or not destinations:
            return {}

        # Mapbox matrix: 1 source × N destinations (max 25 coords total including source)
        batch = destinations[:24]
        coords = ";".join(
            [f"{origin_lon},{origin_lat}"]
            + [f"{lon},{lat}" for _, lat, lon in batch]
        )
        url = f"https://api.mapbox.com/directions-matrix/v1/mapbox/driving/{coords}"
        params = {
            "access_token": token,
            "sources": "0",
            "destinations": ";".join(str(i) for i in range(1, len(batch) + 1)),
            "annotations": "duration",
        }
        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.get(url, params=params)
                response.raise_for_status()
                payload = response.json()
        except Exception:
            logger.exception("mapbox matrix failed")
            return {}

        durations = payload.get("durations") or [[]]
        if not durations or not durations[0]:
            return {}
        row = durations[0]
        out: dict[str, int] = {}
        for index, (key, _, _) in enumerate(batch):
            if index >= len(row):
                break
            seconds = row[index]
            if seconds is None:
                continue
            out[key] = max(1, int(round(float(seconds) / 60.0)))
        return out


def select_routing_provider() -> RoutingProvider:
    mode = (settings.geo_routing_provider or "estimate").lower()
    if mode == "mapbox" and settings.mapbox_access_token:
        return MapboxMatrixProvider()
    if mode == "mapbox":
        logger.warning("geo_routing_provider=mapbox but MAPBOX_ACCESS_TOKEN missing; using estimate")
    return EstimateRoutingProvider()
