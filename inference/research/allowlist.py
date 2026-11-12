"""Allowlist for advisor fetch_url."""

from __future__ import annotations

from urllib.parse import urlparse

# Exact host matches (lowercase, no www.)
_EXACT_HOSTS = frozenset(
    {
        "bls.gov",
        "www.bls.gov",
        "data.bls.gov",
        "levels.fyi",
        "www.levels.fyi",
        "glassdoor.com",
        "www.glassdoor.com",
        "indeed.com",
        "www.indeed.com",
        "linkedin.com",
        "www.linkedin.com",
        "usajobs.gov",
        "www.usajobs.gov",
        "careeronestop.org",
        "www.careeronestop.org",
        "onetcenter.org",
        "www.onetcenter.org",
        "onetonline.org",
        "www.onetonline.org",
        "dol.gov",
        "www.dol.gov",
        "salary.com",
        "www.salary.com",
        "builtin.com",
        "www.builtin.com",
        "remoteok.com",
        "www.remoteok.com",
        "lever.co",
        "boards.greenhouse.io",
        "jobs.ashbyhq.com",
    }
)

# Suffix matches: host == suffix or host.endswith("." + suffix)
_SUFFIX_HOSTS = (
    "bls.gov",
    "gov",  # state / federal labor pages
    "levels.fyi",
    "glassdoor.com",
    "indeed.com",
    "linkedin.com",
    "usajobs.gov",
    "careeronestop.org",
    "onetonline.org",
    "dol.gov",
)


def is_fetch_allowed(url: str) -> bool:
    """True when URL is https and host is on the career-market allowlist."""
    raw = (url or "").strip()
    try:
        parsed = urlparse(raw)
    except Exception:
        return False
    if parsed.scheme != "https":
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    if host in _EXACT_HOSTS:
        return True
    bare = host[4:] if host.startswith("www.") else host
    if bare in _EXACT_HOSTS:
        return True
    # Allowlisted suffixes (incl. all https *.gov for labor / public sector pages).
    return any(bare == suffix or bare.endswith("." + suffix) for suffix in _SUFFIX_HOSTS)
