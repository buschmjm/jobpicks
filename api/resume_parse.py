"""Map extracted resume text (and optional LLM output) to ProfileFact models."""

from __future__ import annotations

import contextlib
from typing import Any

from inference.extraction import extract_resume_profile

from api.resume_sections import EducationEntry, ExperienceEntry, normalize_highlights
from api.resume_struct import StructuredResume, parse_structured_resume
from api.schemas import (
    EducationOut,
    ExperienceOut,
    FactStatus,
    ParsedProfile,
    ProfileFact,
    ProfileIdentity,
    ProfileWebLink,
)

_FACT_STATUS_MAP = {
    "confirmed": FactStatus.confirmed,
    "inferred": FactStatus.inferred,
    "needs_confirmation": FactStatus.needs_confirmation,
}


def _status(raw: dict[str, Any]) -> FactStatus:
    return _FACT_STATUS_MAP.get(str(raw.get("status", "inferred")), FactStatus.inferred)


def _fact(key: str, raw: dict[str, Any]) -> ProfileFact:
    raw_value = raw.get("value")
    if isinstance(raw_value, float):
        value = str(int(raw_value)) if raw_value == int(raw_value) else str(raw_value)
    else:
        value = str(raw_value or "")
    return ProfileFact(key=key, value=value, status=_status(raw))


def profile_from_llm(data: dict[str, Any]) -> ParsedProfile:
    facts: list[ProfileFact] = []

    for key in (
        "full_name",
        "location",
        "summary",
    ):
        raw = data.get(key)
        if isinstance(raw, dict) and raw.get("value"):
            facts.append(_fact(key, raw))

    titles = data.get("job_titles") or []
    if titles and isinstance(titles[0], dict):
        facts.append(_fact("title", titles[0]))

    skill_names = [
        str(item.get("value") or "").strip()
        for item in (data.get("skills") or [])
        if isinstance(item, dict) and item.get("value")
    ]

    summary_raw = data.get("summary")
    raw_summary = ""
    if isinstance(summary_raw, dict):
        raw_summary = str(summary_raw.get("value") or "")

    return ParsedProfile(
        facts=facts,
        skill_names=skill_names,
        raw_summary=raw_summary,
        parse_failed=False,
    )


def parse_resume_text(text: str) -> ParsedProfile:
    """Call Ollama resume parser; raises on failure. Not used on the upload path."""
    if not text.strip():
        raise ValueError("Resume text is empty")
    data = extract_resume_profile(text[:12000])
    return profile_from_llm(data)


def _status_for(value: str, *, confirmed: bool = False) -> FactStatus:
    if not value:
        return FactStatus.needs_confirmation
    return FactStatus.confirmed if confirmed else FactStatus.inferred


def _experience_out(entry: ExperienceEntry) -> ExperienceOut:
    return ExperienceOut(
        title=entry.title,
        company_name=entry.company_name,
        location=entry.location,
        start_date=entry.start_date,
        end_date=entry.end_date,
        is_current=entry.is_current,
        highlights=normalize_highlights(list(entry.highlights or [])),
    )


def _education_out(entry: EducationEntry) -> EducationOut:
    return EducationOut(
        institution=entry.institution,
        degree=entry.degree,
        field=entry.field,
        end_date=entry.end_date,
    )


def _facts_from_structured(parsed: StructuredResume) -> list[ProfileFact]:
    title = parsed.title
    if parsed.experiences:
        title = parsed.experiences[0].title or title
    facts = [
        ProfileFact(key="full_name", value=parsed.full_name, status=_status_for(parsed.full_name)),
        ProfileFact(key="title", value=title, status=_status_for(title)),
        ProfileFact(
            key="email",
            value=parsed.email,
            status=_status_for(parsed.email, confirmed=True),
        ),
        ProfileFact(key="location", value=parsed.location, status=_status_for(parsed.location)),
        ProfileFact(key="summary", value=parsed.summary, status=_status_for(parsed.summary)),
    ]
    if parsed.phone:
        facts.insert(
            3,
            ProfileFact(
                key="phone",
                value=parsed.phone,
                status=_status_for(parsed.phone, confirmed=True),
            ),
        )
    return facts


def _identity_from_structured(parsed: StructuredResume) -> ProfileIdentity:
    from core.profile_identity import normalize_pronouns, normalize_us_phone, normalize_web_url

    phone = ""
    if parsed.phone:
        try:
            phone = normalize_us_phone(parsed.phone)
        except ValueError:
            phone = ""
    links: list[ProfileWebLink] = []
    for item in parsed.links or []:
        url_raw = str(item.get("url") or "").strip()
        if not url_raw:
            continue
        try:
            url = normalize_web_url(url_raw)
        except ValueError:
            continue
        links.append(
            ProfileWebLink(
                title=str(item.get("title") or "").strip()[:128],
                url=url,
            )
        )
    if parsed.linkedin and not any("linkedin.com" in (link.url or "").lower() for link in links):
        with contextlib.suppress(ValueError):
            links.insert(
                0,
                ProfileWebLink(title="LinkedIn", url=normalize_web_url(parsed.linkedin)),
            )
    return ProfileIdentity(
        preferred_name=(parsed.full_name or "").strip()[:256],
        email=(parsed.email or "").strip()[:320],
        phone=phone,
        pronouns=normalize_pronouns(parsed.pronouns or ""),
        show_pronouns=True,
        links=links[:12],
    )


def profile_from_extracted_text(text: str, *, filename: str) -> ParsedProfile:
    """Build an editable profile from PDF/DOCX text. No LLM."""
    cleaned = text.strip()
    structured = parse_structured_resume(cleaned)
    facts = _facts_from_structured(structured)
    excerpt = next((f.value for f in facts if f.key == "summary"), "")
    return ParsedProfile(
        facts=facts,
        skill_names=structured.skills,
        experiences=[_experience_out(entry) for entry in structured.experiences],
        education=[_education_out(entry) for entry in structured.education],
        scraped_identity=_identity_from_structured(structured),
        raw_summary=excerpt,
        parse_failed=not bool(cleaned),
    )


def parse_resume_with_fallback(text: str, *, filename: str) -> ParsedProfile:
    """Onboarding uses extracted file text only — LLM is not on this path."""
    return profile_from_extracted_text(text, filename=filename)
