"""US city/state centroid lookup (no external API)."""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

from ingest.country import US_STATE_ABBREVS

_SEEDS_PATH = Path(__file__).resolve().parents[2] / "seeds" / "us_city_centroids.csv"

# Fallback when CSV row missing — state center approximations (lat, lon)
_STATE_CENTROIDS: dict[str, tuple[float, float]] = {
    "AL": (32.806671, -86.791130),
    "AK": (61.370716, -152.404419),
    "AZ": (33.729759, -111.431221),
    "AR": (34.969704, -92.373123),
    "CA": (36.116203, -119.681564),
    "CO": (39.059811, -105.311104),
    "CT": (41.597782, -72.755371),
    "DE": (39.318523, -75.507141),
    "DC": (38.897438, -77.026817),
    "FL": (27.766279, -81.686783),
    "GA": (33.040619, -83.643074),
    "HI": (21.094318, -157.498337),
    "ID": (44.240459, -114.478828),
    "IL": (40.349457, -88.986137),
    "IN": (39.849426, -86.258278),
    "IA": (42.011539, -93.210526),
    "KS": (38.526600, -96.726486),
    "KY": (37.668140, -84.670067),
    "LA": (31.169546, -91.867805),
    "ME": (44.693947, -69.381927),
    "MD": (39.063946, -76.802101),
    "MA": (42.230171, -71.530106),
    "MI": (43.326618, -84.536095),
    "MN": (45.694454, -93.900192),
    "MS": (32.741646, -89.678696),
    "MO": (38.456085, -92.288368),
    "MT": (46.921925, -110.454353),
    "NE": (41.125370, -98.268082),
    "NV": (38.313515, -117.055374),
    "NH": (43.452492, -71.563896),
    "NJ": (40.298904, -74.521011),
    "NM": (34.840515, -106.248482),
    "NY": (42.165726, -74.948051),
    "NC": (35.630066, -79.806419),
    "ND": (47.528912, -99.784012),
    "OH": (40.388783, -82.764915),
    "OK": (35.565342, -96.928917),
    "OR": (44.572021, -122.070938),
    "PA": (40.590752, -77.209755),
    "RI": (41.680893, -71.511780),
    "SC": (33.856892, -80.945007),
    "SD": (44.299782, -99.438828),
    "TN": (35.747845, -86.692345),
    "TX": (31.054487, -97.563461),
    "UT": (40.150032, -111.862434),
    "VT": (44.045876, -72.710686),
    "VA": (37.769337, -78.169968),
    "WA": (47.400902, -121.490494),
    "WV": (38.491226, -80.954453),
    "WI": (44.268543, -89.616508),
    "WY": (42.755966, -107.302490),
}


def _normalize_city(name: str) -> str:
    return " ".join(name.strip().lower().split())


def _normalize_state(state: str) -> str:
    cleaned = state.strip().upper()
    if len(cleaned) == 2:
        return cleaned
    aliases = {
        "TEXAS": "TX",
        "CALIFORNIA": "CA",
        "NEW YORK": "NY",
        "FLORIDA": "FL",
        "ILLINOIS": "IL",
        "PENNSYLVANIA": "PA",
        "OHIO": "OH",
        "GEORGIA": "GA",
        "NORTH CAROLINA": "NC",
        "MICHIGAN": "MI",
    }
    return aliases.get(cleaned, cleaned[:2] if len(cleaned) >= 2 else cleaned)


@lru_cache(maxsize=1)
def _city_index() -> dict[tuple[str, str], tuple[float, float]]:
    index: dict[tuple[str, str], tuple[float, float]] = {}
    if not _SEEDS_PATH.is_file():
        return index
    with _SEEDS_PATH.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            city = _normalize_city(row["city"])
            state = _normalize_state(row["state"])
            if state not in US_STATE_ABBREVS:
                continue
            index[(city, state)] = (float(row["lat"]), float(row["lon"]))
    return index


def lookup_city_state(city: str | None, state: str | None) -> tuple[float, float] | None:
    if not city or not state:
        return None
    normalized_state = _normalize_state(state)
    if normalized_state not in US_STATE_ABBREVS:
        return None
    coords = _city_index().get((_normalize_city(city), normalized_state))
    if coords is not None:
        return coords
    return _STATE_CENTROIDS.get(normalized_state)


def lookup_location_text(location: str) -> tuple[float, float] | None:
    """Best-effort parse of 'City, ST' or 'City, State, USA' strings."""
    parts = [part.strip() for part in location.split(",") if part.strip()]
    if len(parts) >= 2:
        city = parts[0]
        state_part = parts[1].upper().replace("USA", "").replace("US", "").strip()
        if len(state_part) == 2:
            return lookup_city_state(city, state_part)
        if len(parts) >= 3:
            return lookup_city_state(city, parts[2])
    return None
