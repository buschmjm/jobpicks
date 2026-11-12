"""JSearch / OpenWeb Ninja HTTP error helpers."""

from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class JSearchRequestError(Exception):
    """Structured JSearch HTTP failure for logging and health probes."""

    status_code: int
    url: str
    message: str
    retry_after: float | None = None

    def __str__(self) -> str:
        parts = [f"HTTP {self.status_code}", self.message]
        if self.retry_after is not None:
            parts.append(f"retry_after={self.retry_after}s")
        return " — ".join(parts)


def parse_jsearch_error(response: httpx.Response) -> JSearchRequestError:
    retry_after: float | None = None
    raw_retry = response.headers.get("Retry-After")
    if raw_retry:
        try:
            retry_after = float(raw_retry)
        except ValueError:
            retry_after = None

    message = ""
    try:
        payload = response.json()
        if isinstance(payload, dict):
            message = str(
                payload.get("message")
                or payload.get("error")
                or payload.get("detail")
                or ""
            ).strip()
    except Exception:
        message = (response.text or "").strip()[:300]

    if not message:
        message = response.reason_phrase or "request failed"

    return JSearchRequestError(
        status_code=response.status_code,
        url=str(response.url),
        message=message,
        retry_after=retry_after,
    )
