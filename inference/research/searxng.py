"""SearXNG JSON search client."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import httpx

from inference.config import searxng_base_url

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 12.0
_MAX_RESULTS = 5


def search_web(
    query: str,
    *,
    base_url: str | None = None,
    limit: int = _MAX_RESULTS,
    timeout: float = _DEFAULT_TIMEOUT,
) -> list[dict[str, str]]:
    """Return sanitized search hits: title, url, content, publisher."""
    q = " ".join((query or "").split())[:240]
    if len(q) < 3:
        return []
    root = (base_url or searxng_base_url()).rstrip("/")
    url = f"{root}/search"
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(
                url,
                params={"q": q, "format": "json", "language": "en"},
            )
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        logger.warning("searxng search failed for %r: %s", q, exc)
        return []

    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        return []

    out: list[dict[str, str]] = []
    for row in results:
        if not isinstance(row, dict):
            continue
        href = str(row.get("url") or "").strip()
        title = str(row.get("title") or "").strip()
        content = str(row.get("content") or row.get("snippet") or "").strip()
        if not href or not title:
            continue
        publisher = _publisher_from_url(href)
        out.append(
            {
                "title": title[:200],
                "url": href[:2048],
                "content": content[:400],
                "publisher": publisher,
            }
        )
        if len(out) >= max(1, limit):
            break
    return out


def _publisher_from_url(url: str) -> str:
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return "web"
    host = host.lower()
    if host.startswith("www."):
        host = host[4:]
    return host or "web"


def fetch_url_text(
    url: str,
    *,
    timeout: float = 15.0,
    max_chars: int = 3000,
) -> dict[str, Any] | None:
    """GET a URL and return stripped text payload, or None on failure."""
    href = (url or "").strip()
    if not href.startswith(("http://", "https://")):
        return None
    try:
        with httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "JobDeckAdvisor/1.0 (+https://jobs.jbuschmann.com)"},
        ) as client:
            response = client.get(href)
            response.raise_for_status()
            ctype = (response.headers.get("content-type") or "").lower()
            if "html" not in ctype and "text" not in ctype and "json" not in ctype:
                return None
            text = _html_to_text(response.text)
    except Exception as exc:
        logger.warning("fetch_url failed for %r: %s", href, exc)
        return None
    text = " ".join(text.split())
    if not text:
        return None
    return {
        "url": href[:2048],
        "publisher": _publisher_from_url(href),
        "title": _publisher_from_url(href),
        "content": text[:max_chars],
    }


def _html_to_text(raw: str) -> str:
    """Cheap HTML strip without adding a parser dependency."""
    import re

    cleaned = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", raw)
    cleaned = re.sub(r"(?is)<[^>]+>", " ", cleaned)
    cleaned = cleaned.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<")
    cleaned = cleaned.replace("&gt;", ">").replace("&quot;", '"')
    return cleaned
