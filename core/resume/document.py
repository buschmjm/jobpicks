"""Structured resume documents (schema jobdeck.resume.v1) for ATS HTML export.

Modeled after https://github.com/buschmjm/resume — single-column ATS layout with
named fields so drafts stay JSON-serializable and editable before render.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from core.models import Profile, ProfileEducation, ProfileExperience, ProfileSkill
from core.profile_identity import display_pronouns, identity_contacts, resolve_identity

RESUME_SCHEMA = "jobdeck.resume.v1"

_MONTH_NAMES = (
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def format_resume_date(raw: str | None, *, is_current: bool = False) -> str:
    if is_current or (raw or "").strip().lower() in {"present", "current", "now"}:
        return "Present"
    text = (raw or "").strip()
    if not text:
        return ""
    parts = text.replace("/", "-").split("-")
    try:
        year = int(parts[0])
        month = int(parts[1]) if len(parts) > 1 and parts[1] else 0
    except ValueError:
        return text
    if 1 <= month <= 12:
        return f"{_MONTH_NAMES[month]} {year}"
    return str(year)


def format_job_meta(company: str, location: str, start: str, end: str, is_current: bool) -> str:
    when = " to ".join(
        p
        for p in (
            format_resume_date(start),
            format_resume_date(end, is_current=is_current),
        )
        if p
    )
    place = ", ".join(p for p in (company.strip(), location.strip()) if p)
    if place and when:
        return f"{place} | {when}"
    return place or when


def _selectable(text: str, included: bool = True) -> dict[str, Any]:
    return {"text": text, "included": included}


def _contact_items(email: str | None) -> list[dict[str, Any]]:
    contacts: list[dict[str, Any]] = []
    if email:
        contacts.append({"label": "Email", "value": email, "href": f"mailto:{email}"})
    return contacts


def build_master_document(
    session: Session,
    user_id: uuid.UUID,
    *,
    email: str | None = None,
    full_name: str | None = None,
) -> dict[str, Any]:
    """Build a full resume.v1 document from the user's structured profile."""
    profile = session.scalar(
        select(Profile)
        .where(Profile.user_id == user_id)
        .options(
            selectinload(Profile.experiences),
            selectinload(Profile.education_rows),
            selectinload(Profile.skill_links).selectinload(ProfileSkill.skill),
        )
    )
    if profile is None:
        return empty_document(email=email, full_name=full_name)

    identity = resolve_identity(profile, account_email=email)
    name = (
        full_name
        or identity.get("preferred_name")
        or _name_from_parsed(profile)
        or (email.split("@")[0] if email else "Candidate")
    )
    headline = (profile.headline or "").strip() or "Professional"
    tagline = ""
    if profile.target_titles:
        tagline = ", ".join(str(t) for t in profile.target_titles[:3] if t)

    summary_raw = (profile.summary or "").strip()
    paragraphs = [p.strip() for p in summary_raw.split("\n\n") if p.strip()] if summary_raw else []
    if not paragraphs and summary_raw:
        paragraphs = [summary_raw]

    roles = [
        role_from_experience(exp, included=True, highlight_included=True)
        for exp in sorted(profile.experiences, key=lambda row: row.sort_order)
    ]

    skill_names: list[str] = []
    for link in profile.skill_links:
        if link.skill and link.skill.name:
            skill_names.append(link.skill.name)
    if not skill_names and profile.skills:
        skill_names = [str(s) for s in profile.skills if s]

    skill_groups = (
        [
            {
                "label": "Core Technologies",
                "items": [_selectable(name, True) for name in skill_names[:40]],
            }
        ]
        if skill_names
        else []
    )

    education = [
        education_from_row(row, included=True)
        for row in sorted(profile.education_rows, key=lambda r: r.sort_order)
    ]

    contacts = identity_contacts(identity)
    if not contacts and email:
        contacts = _contact_items(email)

    return {
        "schema": RESUME_SCHEMA,
        "layout": "ats",
        "target": None,
        "rationale": "Full resume built from your saved profile.",
        "header": {
            "full_name": name,
            "headline": headline,
            "tagline": tagline,
            "pronouns": display_pronouns(identity),
            "contacts": contacts,
        },
        "summary_paragraphs": paragraphs,
        "roles": roles,
        "skill_groups": skill_groups,
        "projects": [],
        "education": education,
    }


def empty_document(*, email: str | None = None, full_name: str | None = None) -> dict[str, Any]:
    return {
        "schema": RESUME_SCHEMA,
        "layout": "ats",
        "target": None,
        "rationale": "",
        "header": {
            "full_name": full_name or "Candidate",
            "headline": "",
            "tagline": "",
            "pronouns": "",
            "contacts": _contact_items(email),
        },
        "summary_paragraphs": [],
        "roles": [],
        "skill_groups": [],
        "projects": [],
        "education": [],
    }


def role_from_experience(
    exp: ProfileExperience,
    *,
    included: bool,
    highlight_included: bool | set[int],
) -> dict[str, Any]:
    highlights: list[dict[str, Any]] = []
    for idx, text in enumerate(exp.highlights or []):
        clean = str(text).strip()
        if not clean:
            continue
        on = idx in highlight_included if isinstance(highlight_included, set) else bool(highlight_included)
        highlights.append(_selectable(clean, on))
    return {
        "experience_id": str(exp.id),
        "included": included,
        "title": exp.title,
        "subtitle": None,
        "company_name": exp.company_name,
        "location": exp.location or "",
        "start_date": exp.start_date or "",
        "end_date": exp.end_date or "",
        "is_current": bool(exp.is_current),
        "scope": None,
        "meta": format_job_meta(
            exp.company_name,
            exp.location or "",
            exp.start_date or "",
            exp.end_date or "",
            bool(exp.is_current),
        ),
        "highlights": highlights,
    }


def education_from_row(row: ProfileEducation, *, included: bool) -> dict[str, Any]:
    return {
        "education_id": str(row.id),
        "included": included,
        "institution": row.institution,
        "degree": row.degree or "",
        "field": row.field or "",
        "end_date": row.end_date or "",
    }


def _name_from_parsed(profile: Profile) -> str | None:
    parsed = profile.parsed_resume if isinstance(profile.parsed_resume, dict) else {}
    for fact in parsed.get("facts") or []:
        if not isinstance(fact, dict):
            continue
        if str(fact.get("key", "")).lower() in {"full_name", "name"}:
            value = str(fact.get("value") or "").strip()
            if value:
                return value
    return None


def apply_tailor_selection(
    master: dict[str, Any],
    selection: dict[str, Any],
    *,
    target: dict[str, Any] | None,
) -> dict[str, Any]:
    """Apply LLM (or heuristic) selection onto a master catalog document."""
    doc = dict(master)
    doc["schema"] = RESUME_SCHEMA
    doc["target"] = target
    doc["rationale"] = str(selection.get("rationale") or "").strip()
    if selection.get("summary_paragraphs"):
        paragraphs = [str(p).strip() for p in selection["summary_paragraphs"] if str(p).strip()][:4]
        if paragraphs:
            doc["summary_paragraphs"] = paragraphs

    role_map = {
        str(sel.get("experience_id")): sel
        for sel in (selection.get("role_selections") or [])
        if isinstance(sel, dict) and sel.get("experience_id")
    }
    roles_out: list[dict[str, Any]] = []
    for role in master.get("roles") or []:
        if not isinstance(role, dict):
            continue
        rid = str(role.get("experience_id") or "")
        sel = role_map.get(rid)
        role_copy = dict(role)
        if sel is None:
            role_copy["included"] = False if role_map else bool(role.get("included", True))
            roles_out.append(role_copy)
            continue
        role_copy["included"] = bool(sel.get("include", True))
        indices = sel.get("highlight_indices")
        highlights = list(role.get("highlights") or [])
        if isinstance(indices, list):
            wanted = {int(i) for i in indices if isinstance(i, int) or str(i).isdigit()}
            new_highlights = []
            for idx, item in enumerate(highlights):
                text = item.get("text") if isinstance(item, dict) else str(item)
                new_highlights.append(_selectable(str(text), idx in wanted))
            role_copy["highlights"] = new_highlights
        roles_out.append(role_copy)
    doc["roles"] = roles_out

    skill_wanted = {
        str(s).strip().lower() for s in (selection.get("skill_names") or []) if str(s).strip()
    }
    groups_out: list[dict[str, Any]] = []
    for group in master.get("skill_groups") or []:
        if not isinstance(group, dict):
            continue
        items = []
        for item in group.get("items") or []:
            text = item.get("text") if isinstance(item, dict) else str(item)
            clean = str(text).strip()
            if not clean:
                continue
            included = (clean.lower() in skill_wanted) if skill_wanted else True
            items.append(_selectable(clean, included))
        groups_out.append({"label": group.get("label") or "Skills", "items": items})
    doc["skill_groups"] = groups_out

    edu_indices = selection.get("education_indices")
    education_out: list[dict[str, Any]] = []
    for idx, row in enumerate(master.get("education") or []):
        if not isinstance(row, dict):
            continue
        row_copy = dict(row)
        if isinstance(edu_indices, list):
            wanted = {int(i) for i in edu_indices if isinstance(i, int) or str(i).isdigit()}
            row_copy["included"] = idx in wanted
        education_out.append(row_copy)
    doc["education"] = education_out
    return doc


def included_roles(document: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for role in document.get("roles") or []:
        if isinstance(role, dict) and role.get("included", True):
            highlights = [
                h
                for h in (role.get("highlights") or [])
                if isinstance(h, dict) and h.get("included", True) and h.get("text")
            ]
            copy = dict(role)
            copy["highlights"] = highlights
            out.append(copy)
    return out


def included_skill_groups(document: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for group in document.get("skill_groups") or []:
        if not isinstance(group, dict):
            continue
        items = [
            str(i.get("text"))
            for i in (group.get("items") or [])
            if isinstance(i, dict) and i.get("included", True) and i.get("text")
        ]
        if items:
            out.append({"label": group.get("label") or "Skills", "items": items})
    return out


def included_education(document: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        row
        for row in (document.get("education") or [])
        if isinstance(row, dict) and row.get("included", True)
    ]


def heuristic_tailor_selection(master: dict[str, Any], job_text: str) -> dict[str, Any]:
    """Deterministic fallback: prefer roles/highlights/skills that share JD tokens."""
    tokens = {t for t in _tokens(job_text) if len(t) > 2}
    role_selections = []
    for role in master.get("roles") or []:
        if not isinstance(role, dict):
            continue
        rid = role.get("experience_id")
        highlights = role.get("highlights") or []
        scored: list[tuple[int, int]] = []
        for idx, item in enumerate(highlights):
            text = item.get("text") if isinstance(item, dict) else str(item)
            score = len(tokens & _tokens(str(text)))
            scored.append((score, idx))
        scored.sort(reverse=True)
        keep = [idx for score, idx in scored if score > 0][:6]
        if not keep:
            keep = list(range(min(4, len(highlights))))
        role_selections.append(
            {
                "experience_id": rid,
                "include": True,
                "highlight_indices": keep,
            }
        )

    skill_names: list[str] = []
    for group in master.get("skill_groups") or []:
        for item in group.get("items") or []:
            text = item.get("text") if isinstance(item, dict) else str(item)
            clean = str(text).strip()
            if not clean:
                continue
            if tokens & _tokens(clean) or len(skill_names) < 12:
                skill_names.append(clean)
            if len(skill_names) >= 24:
                break

    return {
        "rationale": (
            "Selected accomplishments and skills that overlap with keywords in the job posting. "
            "Review and adjust before exporting."
        ),
        "summary_paragraphs": list(master.get("summary_paragraphs") or [])[:2],
        "role_selections": role_selections,
        "skill_names": skill_names[:24],
        "education_indices": list(range(len(master.get("education") or []))),
    }


def _tokens(text: str) -> set[str]:
    return {m.group(0).lower() for m in re.finditer(r"[a-zA-Z][a-zA-Z0-9+#.]{1,}", text or "")}
