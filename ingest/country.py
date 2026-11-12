"""US location/country classification for ingest and matching."""

from __future__ import annotations

import re

from ingest.schema import StandardJob

DEFAULT_INGEST_COUNTRY = "US"

US_COUNTRY_ALIASES = frozenset(
    {
        "us",
        "usa",
        "u.s.",
        "u.s.a.",
        "united states",
        "united states of america",
    }
)

US_STATE_ABBREVS = frozenset(
    {
        "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
        "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
        "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
        "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
        "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
        "DC",
    }
)

NON_US_MARKERS = (
    "worldwide",
    "anywhere in the world",
    "anywhere",
    "global",
    "europe",
    "emea",
    "apac",
    "latam",
    "latin america",
    "united kingdom",
    " uk",
    "uk,",
    "uk |",
    "| uk",
    "london",
    "berlin",
    "germany",
    "france",
    "paris",
    "amsterdam",
    "netherlands",
    "canada",
    "toronto",
    "vancouver",
    "montreal",
    "india",
    "bangalore",
    "bengaluru",
    "singapore",
    "australia",
    "sydney",
    "melbourne",
    "mexico",
    "brazil",
    "são paulo",
    "sao paulo",
    "spain",
    "madrid",
    "barcelona",
    "italy",
    "rome",
    "milan",
    "poland",
    "warsaw",
    "ireland",
    "dublin",
    "israel",
    "tel aviv",
    "japan",
    "tokyo",
    "south korea",
    "seoul",
    "china",
    "beijing",
    "shanghai",
    "philippines",
    "argentina",
    "colombia",
    "portugal",
    "lisbon",
    "sweden",
    "stockholm",
    "norway",
    "denmark",
    "finland",
    "switzerland",
    "zurich",
    "austria",
    "vienna",
    "belgium",
    "czech",
    "prague",
    "romania",
    "ukraine",
    "new zealand",
    "south africa",
    "remote - uk",
    "remote - eu",
    "remote - emea",
    "remote - canada",
    "remote - apac",
    "remote - india",
    "remote - australia",
)

US_POSITIVE_MARKERS = (
    "united states",
    " u.s.",
    " u.s.a.",
    " usa",
    "usa,",
    "usa |",
    "| usa",
    "us only",
    "u.s. only",
    "us-based",
    "u.s.-based",
    "remote - us",
    "remote - u.s.",
    "remote us",
    "remote, us",
    "remote (us)",
    "within the us",
    "within the u.s.",
    "must be in the us",
    "must be located in the us",
    "us citizen",
    "u.s. citizen",
)

_US_STATE_SUFFIX = re.compile(r",\s*([A-Z]{2})(?:\s*\|\s*|$)")


def normalize_country(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if cleaned.lower() in US_COUNTRY_ALIASES:
        return DEFAULT_INGEST_COUNTRY
    return cleaned


def infer_country_from_location(location: str) -> str | None:
    """Return 'US', a non-US hint, or None when ambiguous."""
    loc = location.strip()
    if not loc:
        return None

    lower = loc.lower()

    for marker in NON_US_MARKERS:
        if marker in lower:
            return "NON_US"

    for marker in US_POSITIVE_MARKERS:
        if marker in lower:
            return DEFAULT_INGEST_COUNTRY

    parts = [part.strip() for part in loc.split(",") if part.strip()]
    if parts:
        last = parts[-1]
        last_lower = last.lower()
        if last_lower in US_COUNTRY_ALIASES or last_lower == "us":
            return DEFAULT_INGEST_COUNTRY
        if len(last) == 2 and last.upper() in US_STATE_ABBREVS:
            return DEFAULT_INGEST_COUNTRY

    state_match = _US_STATE_SUFFIX.search(loc)
    if state_match and state_match.group(1) in US_STATE_ABBREVS:
        return DEFAULT_INGEST_COUNTRY

    if lower in {"usa", "us", "united states"}:
        return DEFAULT_INGEST_COUNTRY

    return None


def resolve_job_country(*, country: str | None, location: str) -> str | None:
    normalized = normalize_country(country)
    if normalized == DEFAULT_INGEST_COUNTRY:
        return DEFAULT_INGEST_COUNTRY
    if normalized:
        return normalized

    inferred = infer_country_from_location(location)
    if inferred == DEFAULT_INGEST_COUNTRY:
        return DEFAULT_INGEST_COUNTRY
    if inferred == "NON_US":
        return "NON_US"
    return None


def is_us_job(job: StandardJob) -> bool:
    resolved = resolve_job_country(country=job.country, location=job.location)
    if resolved == DEFAULT_INGEST_COUNTRY:
        return True
    if resolved == "NON_US" or (resolved and resolved != DEFAULT_INGEST_COUNTRY):
        return False

    # Aggregators scoped to the US API can be trusted when they did not set country.
    return job.source in {"adzuna", "jsearch", "usajobs"}


def is_us_job_record(*, country: str | None, location: str | None, source: str | None = None) -> bool:
    location_text = location or ""
    resolved = resolve_job_country(country=country, location=location_text)
    if resolved == DEFAULT_INGEST_COUNTRY:
        return True
    if resolved == "NON_US" or (resolved and resolved != DEFAULT_INGEST_COUNTRY):
        return False
    return source in {"adzuna", "jsearch", "usajobs"}


def parse_us_city_state(location: str) -> tuple[str | None, str | None]:
    parts = [part.strip() for part in location.split(",") if part.strip()]
    if len(parts) >= 2 and parts[-1].upper() in US_STATE_ABBREVS:
        return parts[-2], parts[-1].upper()
    return None, None
