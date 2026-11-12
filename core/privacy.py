"""Privacy helpers: data deletion, event anonymization, retention (plan §12)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

# Resume raw files retained max 90 days (plan §12).
RESUME_FILE_MAX_AGE_DAYS = 90

# Anonymize analytics events older than this (keep aggregate counts).
EVENT_ANONYMIZE_AFTER_DAYS = 730

PII_PAYLOAD_KEYS = frozenset(
    {
        "email",
        "name",
        "full_name",
        "first_name",
        "last_name",
        "phone",
        "resume",
        "resume_text",
        "parsed_resume",
        "ip_address",
        "user_agent",
    }
)

EMAIL_RE = re.compile(r"[^@]+@[^@]+\.[^@]+")


def scrub_event_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Remove PII keys from an event payload while preserving aggregate fields."""
    if not payload:
        return {}
    cleaned: dict[str, Any] = {}
    for key, value in payload.items():
        if key.lower() in PII_PAYLOAD_KEYS:
            continue
        if isinstance(value, str) and EMAIL_RE.search(value):
            cleaned[key] = "[redacted]"
        elif isinstance(value, dict):
            nested = scrub_event_payload(value)
            if nested:
                cleaned[key] = nested
        elif isinstance(value, list):
            cleaned[key] = [
                scrub_event_payload(item) if isinstance(item, dict) else item for item in value
            ]
        else:
            cleaned[key] = value
    return cleaned


def anonymized_user_email(user_id: UUID) -> str:
    """Placeholder email after account deletion."""
    return f"deleted-{user_id}@deleted.local"


def resume_storage_cutoff(
    *,
    now: datetime | None = None,
    max_age_days: int = RESUME_FILE_MAX_AGE_DAYS,
) -> datetime:
    """Return cutoff datetime; resume files older than this should be purged."""
    reference = now or datetime.now(UTC)
    return reference - timedelta(days=max_age_days)


def event_anonymize_cutoff(
    *,
    now: datetime | None = None,
    max_age_days: int = EVENT_ANONYMIZE_AFTER_DAYS,
) -> datetime:
    """Return cutoff datetime; events created before this should be anonymized."""
    reference = now or datetime.now(UTC)
    return reference - timedelta(days=max_age_days)


def should_purge_resume_file(
    modified_at: datetime,
    cutoff: datetime,
) -> bool:
    """True when a stored resume file is older than the retention cutoff."""
    if modified_at.tzinfo is None:
        modified_at = modified_at.replace(tzinfo=UTC)
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=UTC)
    return modified_at < cutoff


@dataclass(frozen=True)
class StaleResumeFile:
    path: Path
    modified_at: datetime


def find_stale_resume_files(
    storage_dir: Path,
    cutoff: datetime,
) -> list[StaleResumeFile]:
    """List resume files in storage_dir that exceed the retention window."""
    if not storage_dir.is_dir():
        return []

    stale: list[StaleResumeFile] = []
    for path in storage_dir.iterdir():
        if not path.is_file():
            continue
        modified = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        if should_purge_resume_file(modified, cutoff):
            stale.append(StaleResumeFile(path=path, modified_at=modified))
    return stale


def should_anonymize_event(created_at: datetime, cutoff: datetime) -> bool:
    """True when an analytics event is old enough to anonymize."""
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=UTC)
    return created_at < cutoff
