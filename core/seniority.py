"""Seniority level string ↔ integer mapping (Workstream F1, scale 0–8)."""

from __future__ import annotations

import re

# Shared constant scale (LOCKED):
# 0 intern, 1 junior, 2 mid, 3 senior, 4 lead/staff, 5 manager,
# 6 director/principal, 7 VP, 8 C-suite
SENIORITY_INTERN = 0
SENIORITY_JUNIOR = 1
SENIORITY_MID = 2
SENIORITY_SENIOR = 3
SENIORITY_LEAD_STAFF = 4
SENIORITY_MANAGER = 5
SENIORITY_DIRECTOR_PRINCIPAL = 6
SENIORITY_VP = 7
SENIORITY_C_SUITE = 8

_LEVEL_MAP: dict[str, int] = {
    "intern": SENIORITY_INTERN,
    "junior": SENIORITY_JUNIOR,
    "jr": SENIORITY_JUNIOR,
    "mid": SENIORITY_MID,
    "middle": SENIORITY_MID,
    "senior": SENIORITY_SENIOR,
    "sr": SENIORITY_SENIOR,
    "lead": SENIORITY_LEAD_STAFF,
    "staff": SENIORITY_LEAD_STAFF,
    "manager": SENIORITY_MANAGER,
    "director": SENIORITY_DIRECTOR_PRINCIPAL,
    "principal": SENIORITY_DIRECTOR_PRINCIPAL,
    "vp": SENIORITY_VP,
    "vice president": SENIORITY_VP,
    "ceo": SENIORITY_C_SUITE,
    "cto": SENIORITY_C_SUITE,
    "cfo": SENIORITY_C_SUITE,
    "coo": SENIORITY_C_SUITE,
    "chief": SENIORITY_C_SUITE,
    "president": SENIORITY_C_SUITE,
    "partner": SENIORITY_C_SUITE,
    "owner": SENIORITY_C_SUITE,
}

# Order matters: match longer / more specific patterns first.
_TITLE_RULES: tuple[tuple[re.Pattern[str], int], ...] = (
    (re.compile(r"\b(intern|internship)\b", re.I), SENIORITY_INTERN),
    (re.compile(r"\b(junior|jr\.?)\b", re.I), SENIORITY_JUNIOR),
    (re.compile(r"\b(ceo|cto|cfo|coo|chief|president|partner|owner)\b", re.I), SENIORITY_C_SUITE),
    (re.compile(r"\b(vp|vice president)\b", re.I), SENIORITY_VP),
    (re.compile(r"\b(director|principal)\b", re.I), SENIORITY_DIRECTOR_PRINCIPAL),
    (re.compile(r"\bmanager\b", re.I), SENIORITY_MANAGER),
    (re.compile(r"\b(lead|staff)\b", re.I), SENIORITY_LEAD_STAFF),
    (re.compile(r"\b(senior|sr\.?)\b", re.I), SENIORITY_SENIOR),
)


def derive_seniority_from_title(title: str) -> int:
    """Derive seniority level 0–8 from a job or profile title string."""
    text = (title or "").strip()
    if not text:
        return SENIORITY_MID
    for pattern, level in _TITLE_RULES:
        if pattern.search(text):
            return level
    return SENIORITY_MID


def seniority_to_int(value: str | int | None) -> int:
    """Map stored seniority label or integer to the shared 0–8 scale."""
    if isinstance(value, int):
        return max(SENIORITY_INTERN, min(SENIORITY_C_SUITE, value))
    if not value:
        return SENIORITY_MID
    lowered = str(value).lower().strip()
    if lowered.isdigit():
        return max(SENIORITY_INTERN, min(SENIORITY_C_SUITE, int(lowered)))
    for key, level in sorted(_LEVEL_MAP.items(), key=lambda item: -len(item[0])):
        if key in lowered:
            return level
    return derive_seniority_from_title(lowered)


def seniority_label(level: int) -> str:
    labels = {
        0: "intern",
        1: "junior",
        2: "mid",
        3: "senior",
        4: "lead/staff",
        5: "manager",
        6: "director/principal",
        7: "vp",
        8: "c-suite",
    }
    return labels.get(level, "mid")
