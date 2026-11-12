"""Helpers for detecting and resolving truncated job descriptions."""

from __future__ import annotations

from ingest.pipeline import normalize_text

_TRUNCATED_SUFFIXES = ("…", "...")
_ADZUNA_SNIPPET_LEN = 500


def description_looks_truncated(text: str | None) -> bool:
    """True when text is likely an API snippet rather than a full posting."""
    if not text:
        return False
    trimmed = text.strip()
    if not trimmed:
        return False
    if trimmed.endswith(_TRUNCATED_SUFFIXES):
        return True
    return len(trimmed) == _ADZUNA_SNIPPET_LEN and trimmed[-1] not in ".!?"


def token_similarity(left: str, right: str) -> float:
    """Jaccard similarity on normalized word tokens."""
    left_tokens = set(normalize_text(left).split())
    right_tokens = set(normalize_text(right).split())
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def descriptions_match_job(
    *,
    job_title: str,
    company_name: str,
    candidate_title: str,
    candidate_company: str,
) -> bool:
    title_score = token_similarity(job_title, candidate_title)
    company_score = token_similarity(company_name, candidate_company)
    return title_score >= 0.6 and company_score >= 0.45


def prefer_description(current: str | None, candidate: str | None) -> str | None:
    """Pick the richer description when merging job records."""
    current_text = (current or "").strip()
    candidate_text = (candidate or "").strip()
    if not candidate_text:
        return current_text or None
    if not current_text:
        return candidate_text
    if description_looks_truncated(candidate_text) and not description_looks_truncated(current_text):
        return current_text
    if description_looks_truncated(current_text) and not description_looks_truncated(candidate_text):
        return candidate_text
    if len(candidate_text) > len(current_text) + 80:
        return candidate_text
    return current_text
