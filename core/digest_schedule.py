"""Digest send-window helpers (Workstream C3 — per-timezone morning send)."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

DEFAULT_DIGEST_TIMEZONE = "America/Chicago"
DIGEST_LOCAL_HOUR = 6


def digest_timezone_for_user(timezone: str | None) -> str:
    if timezone and timezone.strip():
        return timezone.strip()
    return DEFAULT_DIGEST_TIMEZONE


def is_digest_send_window(
    *,
    timezone: str | None,
    now: datetime,
    local_hour: int = DIGEST_LOCAL_HOUR,
) -> bool:
    """True when the user's local clock is in the digest hour (default 6:00–6:59)."""
    tz_name = digest_timezone_for_user(timezone)
    try:
        local = now.astimezone(ZoneInfo(tz_name))
    except Exception:
        local = now.astimezone(ZoneInfo(DEFAULT_DIGEST_TIMEZONE))
    return local.hour == local_hour
