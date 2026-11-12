"""Simple in-memory rate limiting for auth endpoints (v1)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class RateLimiter:
    """Fixed-window counter per key."""

    max_requests: int
    window_seconds: int
    _windows: dict[str, tuple[int, float]] = field(default_factory=dict)

    def would_allow(self, key: str) -> bool:
        now = time.monotonic()
        count, window_start = self._windows.get(key, (0, now))
        if now - window_start >= self.window_seconds:
            return True
        return count < self.max_requests

    def allow(self, key: str) -> bool:
        if not self.would_allow(key):
            return False
        self.record(key)
        return True

    def record(self, key: str) -> None:
        now = time.monotonic()
        count, window_start = self._windows.get(key, (0, now))
        if now - window_start >= self.window_seconds:
            count, window_start = 0, now
        self._windows[key] = (count + 1, window_start)


# plan §12: max 3 requests/email/hour, max 10/IP/hour
_magic_link_by_email = RateLimiter(max_requests=3, window_seconds=3600)
_magic_link_by_ip = RateLimiter(max_requests=10, window_seconds=3600)


def check_magic_link_rate_limit(*, email: str, client_ip: str | None) -> None:
    from fastapi import HTTPException, status

    email_key = email.strip().lower()
    if not _magic_link_by_email.would_allow(email_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many sign-in requests for this email. Try again in about an hour.",
        )
    if client_ip and not _magic_link_by_ip.would_allow(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many sign-in requests from this network. Try again in about an hour.",
        )


def record_magic_link_request(*, email: str, client_ip: str | None) -> None:
    """Count a successful magic-link send against rate limits."""
    _magic_link_by_email.record(email.strip().lower())
    if client_ip:
        _magic_link_by_ip.record(client_ip)
