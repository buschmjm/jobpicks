"""Cover letter drafting for application packets."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from inference.client import InferenceUnavailableError, get_client
from inference.extraction import ExtractionError, _chat_json
from inference.prompts import load_prompt

logger = logging.getLogger(__name__)

_BANNED_OPENERS = (
    "i am writing to express my interest",
    "i am excited to apply",
    "i am thrilled",
    "with great enthusiasm",
)


def _preferred_name(identity: dict[str, Any]) -> str:
    for key in ("preferred_name", "full_name", "name"):
        value = str(identity.get(key) or "").strip()
        if value:
            return value
    return "Candidate"


def _profile_summary(profile: dict[str, Any]) -> str:
    overview = profile.get("profile_overview")
    if isinstance(overview, dict):
        summary = str(overview.get("summary") or "").strip()
        if summary:
            return summary
    return str(profile.get("summary") or "").strip()


def _role_highlights(profile: dict[str, Any], *, limit: int = 4) -> list[str]:
    highlights: list[str] = []
    roles = profile.get("roles")
    if not isinstance(roles, list):
        return highlights
    for role in roles:
        if not isinstance(role, dict):
            continue
        for item in role.get("highlights") or []:
            text = str(item or "").strip()
            if text and text not in highlights:
                highlights.append(text)
            if len(highlights) >= limit:
                return highlights
    return highlights


def _matching_skills(profile: dict[str, Any], job: dict[str, Any], *, limit: int = 4) -> list[str]:
    skills = profile.get("skills")
    if not isinstance(skills, list):
        return []
    description = str(job.get("description") or "").lower()
    if not description:
        return [str(skill) for skill in skills[:limit] if str(skill).strip()]
    matched: list[str] = []
    for skill in skills:
        name = str(skill or "").strip()
        if not name:
            continue
        if name.lower() in description:
            matched.append(name)
        if len(matched) >= limit:
            break
    if matched:
        return matched
    return [str(skill) for skill in skills[:limit] if str(skill).strip()]


def _recent_role(profile: dict[str, Any]) -> dict[str, Any]:
    roles = profile.get("roles")
    if isinstance(roles, list):
        for role in roles:
            if isinstance(role, dict):
                return role
    return {}


def _is_weak_letter(text: str) -> bool:
    cleaned = (text or "").strip()
    if len(cleaned) < 280:
        return True
    lowered = cleaned.lower()
    if any(opener in lowered for opener in _BANNED_OPENERS):
        return True
    if cleaned.count("\n\n") < 2:
        return True
    return False


def template_cover_letter(
    *,
    profile: dict[str, Any],
    identity: dict[str, Any],
    job: dict[str, Any],
    fit_rationale: list[str] | None = None,
) -> str:
    """Deterministic cover letter from profile roles and job posting."""
    name = _preferred_name(identity)
    title = str(job.get("title") or "this role").strip()
    company = str(job.get("company") or "your organization").strip()
    summary = _profile_summary(profile)
    role = _recent_role(profile)
    role_title = str(role.get("job_title") or "my recent role").strip()
    employer = str(role.get("employer") or "my current employer").strip()
    highlights = _role_highlights(profile)
    skills = _matching_skills(profile, job)

    opening = (
        f"Dear Hiring Manager,\n\n"
        f"I am applying for the {title} role at {company}. "
    )
    if summary:
        opening += summary
    else:
        opening += (
            f"As {role_title} at {employer}, I have delivered results that map directly "
            f"to the responsibilities outlined in your posting."
        )

    body_parts: list[str] = []
    if highlights:
        body_parts.append(
            "In recent roles, relevant accomplishments include: "
            + "; ".join(highlights[:3])
            + "."
        )
    if skills:
        body_parts.append(
            f"The posting emphasizes {', '.join(skills)}, which are core strengths in my background."
        )
    if fit_rationale:
        rationale = str(fit_rationale[0]).strip()
        if rationale and len(body_parts) < 2:
            body_parts.append(rationale)

    if not body_parts:
        body_parts.append(
            f"My experience in {role_title.lower()} has prepared me to contribute quickly in this position."
        )

    closing = (
        f"I would welcome a conversation about how I can help {company} succeed in this role. "
        f"Thank you for your time and consideration.\n\n"
        f"Sincerely,\n{name}"
    )

    return "\n\n".join([opening, *body_parts, closing]).strip()


def draft_cover_letter(
    *,
    profile: dict[str, Any],
    identity: dict[str, Any],
    job: dict[str, Any],
    fit_rationale: list[str] | None = None,
) -> str:
    """Return a tailored cover letter using the LLM with a profile-rich template fallback."""
    fallback = template_cover_letter(
        profile=profile,
        identity=identity,
        job=job,
        fit_rationale=fit_rationale,
    )

    loaded = load_prompt("cover_letter")
    payload = {
        "identity": identity,
        "profile": profile,
        "job": job,
        "fit_rationale": fit_rationale or [],
    }
    user_content = json.dumps(payload, ensure_ascii=False)
    try:
        client = get_client()
        data = _chat_json(client, loaded, user_content)
        letter = str(data.get("cover_letter") or "").strip()
        letter = re.sub(r"\n{3,}", "\n\n", letter)
        if _is_weak_letter(letter):
            logger.info("cover letter LLM output weak, using template fallback")
            return fallback
        return letter
    except (InferenceUnavailableError, ExtractionError, Exception) as exc:
        logger.warning("cover letter LLM unavailable, using template: %s", exc)
        return fallback
