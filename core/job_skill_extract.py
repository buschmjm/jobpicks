"""Heuristic skill and seniority extraction when LLM normalization is unavailable."""

from __future__ import annotations

import re

_SKILL_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bpython\b", re.I), "python"),
    (re.compile(r"\b(?:javascript|typescript|node\.?js)\b", re.I), "javascript"),
    (re.compile(r"\b(?:react|reactjs)\b", re.I), "react"),
    (re.compile(r"\b(?:kubernetes|k8s)\b", re.I), "kubernetes"),
    (re.compile(r"\b(?:aws|amazon web services)\b", re.I), "aws"),
    (re.compile(r"\b(?:gcp|google cloud)\b", re.I), "gcp"),
    (re.compile(r"\bazure\b", re.I), "azure"),
    (re.compile(r"\b(?:postgres|postgresql)\b", re.I), "postgresql"),
    (re.compile(r"\b(?:sql|mysql)\b", re.I), "sql"),
    (re.compile(r"\bdocker\b", re.I), "docker"),
    (re.compile(r"\bterraform\b", re.I), "terraform"),
    (re.compile(r"\b(?:ci/?cd|continuous integration)\b", re.I), "ci/cd"),
    (re.compile(r"\bdevops\b", re.I), "devops"),
    (re.compile(r"\bsalesforce\b", re.I), "salesforce"),
    (re.compile(r"\bsap\b", re.I), "sap"),
    (re.compile(r"\bservicenow\b", re.I), "servicenow"),
    (re.compile(r"\bworkday\b", re.I), "workday"),
    (re.compile(r"\b(?:iam|identity and access)\b", re.I), "iam"),
    (re.compile(r"\b(?:grafana|prometheus|observability)\b", re.I), "observability"),
    (re.compile(r"\b(?:agile|scrum)\b", re.I), "agile"),
    (re.compile(r"\b(?:stakeholder|cross[- ]functional)\b", re.I), "cross-functional coordination"),
    (re.compile(r"\bprogram management\b", re.I), "program management"),
    (re.compile(r"\bproduct management\b", re.I), "product management"),
    (re.compile(r"\b(?:business systems|enterprise applications)\b", re.I), "business systems"),
)

_SENIORITY_TITLE_PATTERN = re.compile(
    r"\b(intern|junior|mid[- ]level|senior|staff|principal|lead|director|manager|head)\b",
    re.I,
)

_REMOTE_PATTERN = re.compile(r"\b(remote|work from home|wfh|hybrid|on[- ]site|onsite)\b", re.I)


def extract_skills_from_text(text: str, *, limit: int = 24) -> list[str]:
    if not text.strip():
        return []
    found: list[str] = []
    seen: set[str] = set()
    for pattern, skill in _SKILL_PATTERNS:
        if pattern.search(text) and skill not in seen:
            seen.add(skill)
            found.append(skill)
        if len(found) >= limit:
            break
    return found


def infer_seniority_label(title: str, description: str = "") -> str | None:
    blob = f"{title}\n{description}"
    match = _SENIORITY_TITLE_PATTERN.search(blob)
    if not match:
        return None
    token = match.group(1).lower().replace("-", " ")
    if token in {"manager", "head", "director"}:
        return "senior"
    if token == "mid level":
        return "mid"
    return token.replace(" ", "")


def infer_work_arrangement(title: str, description: str = "") -> str | None:
    blob = f"{title}\n{description}".lower()
    if "remote" in blob or "work from home" in blob or "wfh" in blob:
        return "remote"
    if "hybrid" in blob:
        return "hybrid"
    if "on-site" in blob or "onsite" in blob:
        return "onsite"
    if _REMOTE_PATTERN.search(blob):
        return "remote"
    return None


def heuristic_normalize_text(title: str, description: str = "") -> dict[str, object]:
    """Best-effort structured fields without LLM."""
    blob = f"{title}\n{description}"
    skills = extract_skills_from_text(blob)
    seniority = infer_seniority_label(title, description)
    arrangement = infer_work_arrangement(title, description)
    payload: dict[str, object] = {"required_skills": skills}
    if seniority:
        payload["seniority_level"] = seniority
    if arrangement:
        payload["work_arrangement"] = arrangement
    return payload
