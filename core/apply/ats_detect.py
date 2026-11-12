"""ATS detection and apply URL intelligence."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

_ATS_HOSTS: tuple[tuple[str, str], ...] = (
    ("boards.greenhouse.io", "greenhouse"),
    ("job-boards.greenhouse.io", "greenhouse"),
    ("jobs.lever.co", "lever"),
    ("jobs.eu.lever.co", "lever"),
    ("jobs.ashbyhq.com", "ashby"),
    ("myworkdayjobs.com", "workday"),
)

_DIRECT_ATS_PRIORITY: tuple[str, ...] = (
    "greenhouse",
    "lever",
    "ashby",
    "workday",
)

_AGGREGATOR_HOST_FRAGMENTS = (
    "linkedin.com",
    "indeed.com",
    "glassdoor.com",
    "ziprecruiter.com",
    "monster.com",
    "google.com",
)

_GH_PATH = re.compile(r"/([^/]+)/jobs/(\d+)", re.I)
_LEVER_PATH = re.compile(r"jobs(?:\.eu)?\.lever\.co/([^/]+)/([0-9a-f-]{36})", re.I)
_ASHBY_PATH = re.compile(r"jobs\.ashbyhq\.com/([^/]+)/([0-9a-f-]{36})", re.I)


def detect_ats_type(url: str) -> str | None:
    """Return ATS slug for a URL host, if recognized."""
    return detect_ats(url)[0]


def detect_ats(url: str) -> tuple[str | None, dict[str, Any]]:
    """Detect ATS type and extract metadata from an apply URL."""
    parsed = urlparse((url or "").strip())
    host = (parsed.netloc or "").lower()
    path = parsed.path or ""
    full = f"{host}{path}"

    ats_type: str | None = None
    for fragment, name in _ATS_HOSTS:
        if fragment in host:
            ats_type = name
            break

    metadata: dict[str, Any] = {"host": host, "path": path}
    if ats_type == "greenhouse":
        match = _GH_PATH.search(path)
        if match:
            metadata["board_token"] = match.group(1)
            metadata["posting_id"] = match.group(2)
    elif ats_type == "lever":
        match = _LEVER_PATH.search(full)
        if match:
            metadata["site_slug"] = match.group(1)
            metadata["posting_id"] = match.group(2)
    elif ats_type == "ashby":
        match = _ASHBY_PATH.search(full)
        if match:
            metadata["org_slug"] = match.group(1)
            metadata["posting_id"] = match.group(2)

    return ats_type, metadata


def resolve_apply_url(*, source_url: str, apply_url: str | None = None) -> str:
    """Prefer explicit apply_url, fall back to source_url."""
    explicit = (apply_url or "").strip()
    if explicit:
        return explicit
    return (source_url or "").strip()


def pick_best_jsearch_apply_link(
    *,
    apply_link: str,
    apply_options: list[dict[str, Any]] | None,
    google_link: str | None = None,
) -> tuple[str, str | None, dict[str, Any]]:
    """Choose the best direct ATS apply link from JSearch options."""
    candidates: list[tuple[str, str | None, dict[str, Any]]] = []

    def add_candidate(link: str) -> None:
        link = (link or "").strip()
        if not link:
            return
        ats_type, metadata = detect_ats(link)
        if ats_type:
            candidates.append((link, ats_type, metadata))
        elif not any(fragment in link.lower() for fragment in _AGGREGATOR_HOST_FRAGMENTS):
            candidates.append((link, None, {}))

    if apply_link:
        add_candidate(apply_link)

    for option in apply_options or []:
        if not isinstance(option, dict):
            continue
        add_candidate(str(option.get("apply_link") or option.get("link") or ""))

    for ats in _DIRECT_ATS_PRIORITY:
        for link, ats_type, metadata in candidates:
            if ats_type == ats:
                return link, ats_type, metadata

    if candidates:
        link, ats_type, metadata = candidates[0]
        return link, ats_type, metadata

    fallback = (apply_link or google_link or "").strip()
    ats_type, metadata = detect_ats(fallback)
    return fallback, ats_type, metadata


def enrich_standard_job_apply(
    *,
    source_url: str,
    apply_url: str | None = None,
    ats_type: str | None = None,
    ats_metadata: dict[str, Any] | None = None,
) -> tuple[str, str | None, dict[str, Any]]:
    """Resolve apply_url + ATS metadata for persistence."""
    resolved_apply = resolve_apply_url(source_url=source_url, apply_url=apply_url)
    detected_type, detected_meta = detect_ats(resolved_apply)
    final_type = ats_type or detected_type
    merged_meta = {**detected_meta, **(ats_metadata or {})}
    return resolved_apply, final_type, merged_meta
