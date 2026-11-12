"""Follow a single redirect hop to resolve aggregator links to final apply URLs."""

from __future__ import annotations

import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def resolve_redirect_url(url: str, *, timeout: float = 8.0) -> str:
    """Follow up to one redirect and return the final URL. Best-effort."""
    target = (url or "").strip()
    if not target:
        return target
    try:
        import httpx
    except ImportError:
        return target

    try:
        with httpx.Client(follow_redirects=True, timeout=timeout) as client:
            response = client.head(target)
            if response.status_code >= 400:
                response = client.get(target)
            final = str(response.url)
            if final and urlparse(final).netloc:
                return final
    except Exception as exc:
        logger.debug("redirect resolve failed for %s: %s", target, exc)
    return target
