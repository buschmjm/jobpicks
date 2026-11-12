"""Tests for truncated job description helpers."""

from __future__ import annotations

from core.job_description import description_looks_truncated, prefer_description


def test_description_looks_truncated_detects_adzuna_snippet() -> None:
    snippet = "A" * 499 + "…"
    assert description_looks_truncated(snippet)
    assert not description_looks_truncated("A" * 1200)


def test_prefer_description_keeps_longer_non_truncated_text() -> None:
    short = "A" * 499 + "…"
    long = ("Full posting body. " * 80).strip()
    assert prefer_description(short, long) == long
    assert prefer_description(long, short) == long
