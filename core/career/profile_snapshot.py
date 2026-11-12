"""Build compact profile snapshots for career-assistant LLM calls."""

from __future__ import annotations

import re
import uuid
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from core.models import Profile, Skill

_MONTH = re.compile(r"^(\d{4})(?:[-/](\d{1,2}))?(?:[-/](\d{1,2}))?$")
_PRESENT = frozenset({"present", "current", "now", "today"})


def _fact_value(parsed_resume: dict[str, Any] | None, key: str) -> str | None:
    if not parsed_resume:
        return None
    facts = parsed_resume.get("facts") or []
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        if str(fact.get("key", "")).lower() == key.lower():
            value = fact.get("value")
            if value is not None and str(value).strip():
                return str(value).strip()
    return None


def parse_work_date(raw: str | None, *, end: bool = False) -> date | None:
    """Parse resume-ish dates (YYYY, YYYY-MM, YYYY-MM-DD, present)."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if text.lower() in _PRESENT:
        return date.today()
    match = _MONTH.match(text)
    if not match:
        return None
    year = int(match.group(1))
    month = int(match.group(2) or (12 if end else 1))
    day = int(match.group(3) or (28 if end else 1))
    month = min(max(month, 1), 12)
    day = min(max(day, 1), 28)
    try:
        return date(year, month, day)
    except ValueError:
        return None


def tenure_years_approx(
    start_raw: str | None,
    end_raw: str | None,
    *,
    is_current: bool = False,
) -> float | None:
    """Approximate years in a single role from structured start/end fields."""
    start = parse_work_date(start_raw, end=False)
    if start is None:
        return None
    if is_current or (end_raw and str(end_raw).strip().lower() in _PRESENT):
        end: date | None = date.today()
    else:
        end = parse_work_date(end_raw, end=True)
    if end is None or end < start:
        return None
    days = (end - start).days
    return round(days / 365.25, 1)


def snapshot_total_years(snapshot: dict[str, Any]) -> float | None:
    totals = snapshot.get("career_totals")
    if isinstance(totals, dict):
        value = totals.get("years_across_all_roles")
        if isinstance(value, (int, float)):
            return float(value)
    legacy = snapshot.get("years_experience")
    if isinstance(legacy, (int, float)):
        return float(legacy)
    return None


def snapshot_roles(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    roles = snapshot.get("roles")
    if isinstance(roles, list):
        return [row for row in roles if isinstance(row, dict)]
    experiences = snapshot.get("experiences") or []
    out: list[dict[str, Any]] = []
    for idx, exp in enumerate(experiences):
        if not isinstance(exp, dict):
            continue
        out.append(
            {
                "index": idx,
                "job_title": exp.get("title"),
                "employer": exp.get("company"),
                "location": exp.get("location"),
                "employment": {
                    "start": exp.get("start_date"),
                    "end": exp.get("end_date"),
                    "is_current": bool(exp.get("is_current")),
                    "tenure_years_approx": exp.get("tenure_years_approx"),
                },
                "highlights": list(exp.get("highlights") or []),
            }
        )
    return out


def snapshot_target_titles(snapshot: dict[str, Any]) -> list[str]:
    prefs = snapshot.get("preferences")
    if isinstance(prefs, dict):
        titles = prefs.get("target_titles") or []
        if titles:
            return [str(t) for t in titles]
    return [str(t) for t in (snapshot.get("existing_target_titles") or [])]


def build_profile_snapshot(
    session: Session,
    user_id: uuid.UUID,
    *,
    goals: str | None = None,
) -> dict[str, Any]:
    """Assemble a nested JSON profile for career LLM prompts.

    Keeps career-wide totals separate from per-role employment windows so the
    model cannot treat total years as tenure in the latest title.
    """
    profile = session.scalar(
        select(Profile)
        .where(Profile.user_id == user_id)
        .options(
            selectinload(Profile.experiences),
            selectinload(Profile.education_rows),
            selectinload(Profile.skill_links),
        )
    )
    if profile is None:
        return {
            "schema": "jobdeck.profile.v2",
            "preferences": {"goals_override": goals.strip() if goals else None},
        }

    skill_names: list[str] = []
    if profile.skill_links:
        skill_ids = [link.skill_id for link in profile.skill_links]
        rows = session.scalars(select(Skill).where(Skill.id.in_(skill_ids))).all()
        skill_names = [row.name for row in rows][:30]
    elif profile.skills:
        skill_names = list(profile.skills)[:30]

    parsed = profile.parsed_resume if isinstance(profile.parsed_resume, dict) else {}
    roles: list[dict[str, Any]] = []
    for idx, exp in enumerate(sorted(profile.experiences, key=lambda row: row.sort_order)[:8]):
        is_current = bool(exp.is_current)
        end_label = "present" if is_current else (exp.end_date or None)
        tenure = tenure_years_approx(exp.start_date, exp.end_date, is_current=is_current)
        roles.append(
            {
                "index": idx,
                "job_title": exp.title,
                "employer": exp.company_name,
                "location": exp.location,
                "employment": {
                    "start": exp.start_date,
                    "end": end_label,
                    "is_current": is_current,
                    "tenure_years_approx": tenure,
                },
                "highlights": list(exp.highlights or [])[:4],
            }
        )

    education = [
        {
            "institution": row.institution,
            "degree": row.degree,
            "field": row.field,
            "end_date": row.end_date,
        }
        for row in sorted(profile.education_rows, key=lambda row: row.sort_order)[:4]
    ]

    total_years = profile.years_experience
    if total_years is None:
        years_raw = _fact_value(parsed, "years_experience")
        if years_raw:
            try:
                total_years = float(years_raw)
            except ValueError:
                total_years = None

    return {
        "schema": "jobdeck.profile.v2",
        "career_totals": {
            "years_across_all_roles": total_years,
            "role_count": len(roles),
            "note": (
                "years_across_all_roles is total career length across every job. "
                "It is NOT years in the current or latest title. "
                "Use roles[].employment.tenure_years_approx for time in each role."
            ),
        },
        "profile_overview": {
            "headline": profile.headline,
            "summary": profile.summary or _fact_value(parsed, "summary"),
            "seniority_level": profile.seniority_level or _fact_value(parsed, "seniority_level"),
        },
        "roles": roles,
        "education": education,
        "skills": skill_names,
        "preferences": {
            "target_titles": list(profile.target_titles or [])[:20],
            "locations": list(profile.locations or [])[:12],
            "remote_preference": profile.remote_preference,
            "saved_goals": profile.free_text_wants,
            "goals_override": goals.strip() if goals and goals.strip() else None,
        },
    }
