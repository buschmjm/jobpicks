"""Validate and apply resume builder profile change proposals."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from core.company_directory import get_or_create_company
from core.models import EventType, Profile, ProfileEducation, ProfileExperience
from core.profile_embed import embed_profile
from core.profile_identity import get_identity_dict, set_identity_dict
from core.profile_resume import list_profile_experiences
from core.skill_directory import replace_profile_skills, resolve_skill_names
from pydantic import TypeAdapter
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.repositories.events_repo import EventsRepository
from api.repositories.profile_repo import ProfileRepository
from api.repositories.resume_message_repo import ResumeMessageRepository
from api.repositories.resume_proposal_repo import ResumeProposalRepository
from api.resume_sections import normalize_highlights
from api.schemas import (
    AddContactLinkOperation,
    AddEducationOperation,
    AddExperienceOperation,
    AppendHighlightsOperation,
    RemoveExperienceOperation,
    ReplaceHighlightsOperation,
    ResumeProposalApplyResponse,
    ResumeProposalListResponse,
    ResumeProposalOperation,
    ResumeProposalResponse,
    ResumeProposalStatus,
    SetHeadlineOperation,
    SetIdentityOperation,
    SetSkillsOperation,
    SetSummaryOperation,
    UpdateEducationOperation,
    UpdateExperienceOperation,
)

_OPERATION_ADAPTER: TypeAdapter[ResumeProposalOperation] = TypeAdapter(ResumeProposalOperation)
_MAX_EXPERIENCES = 12
_MAX_EDUCATION = 8


def validate_operations(raw: list[dict[str, Any]]) -> list[ResumeProposalOperation]:
    """Parse and validate proposal operations from JSONB storage."""
    return [_OPERATION_ADAPTER.validate_python(item) for item in raw]


def _proposal_response(row: Any) -> ResumeProposalResponse:
    ops = validate_operations(list(row.operations or []))
    return ResumeProposalResponse(
        id=row.id,
        variant_id=row.variant_id,
        message_id=row.message_id,
        status=ResumeProposalStatus(row.status),
        proposal_type=row.proposal_type,
        operations=ops,
        preview_summary=row.preview_summary or "",
        applied_at=row.applied_at,
        created_at=row.created_at,
    )


def preview(operations: list[dict[str, Any]]) -> str:
    """Build a human-readable summary of proposed changes."""
    validated = validate_operations(operations)
    lines: list[str] = []
    for op in validated:
        if isinstance(op, SetIdentityOperation):
            name = (op.identity.preferred_name or "").strip()
            lines.append(f"Update contact identity{f' ({name})' if name else ''}")
        elif isinstance(op, SetSummaryOperation):
            snippet = op.summary.strip()[:80]
            lines.append(f"Set summary: {snippet}{'…' if len(op.summary.strip()) > 80 else ''}")
        elif isinstance(op, SetHeadlineOperation):
            lines.append(f"Set headline: {op.headline.strip()}")
        elif isinstance(op, AddExperienceOperation):
            exp = op.experience
            lines.append(f"Add experience: {exp.title.strip()} at {exp.company_name.strip()}")
        elif isinstance(op, UpdateExperienceOperation):
            exp = op.experience
            lines.append(f"Update experience: {exp.title.strip()} at {exp.company_name.strip()}")
        elif isinstance(op, AppendHighlightsOperation):
            lines.append(f"Append {len(op.highlights)} highlight(s) to experience")
        elif isinstance(op, ReplaceHighlightsOperation):
            lines.append(f"Replace highlights on experience ({len(op.highlights)} bullet(s))")
        elif isinstance(op, RemoveExperienceOperation):
            lines.append("Remove an experience entry")
        elif isinstance(op, AddEducationOperation):
            edu = op.education
            lines.append(f"Add education: {edu.institution.strip()}")
        elif isinstance(op, UpdateEducationOperation):
            edu = op.education
            lines.append(f"Update education: {edu.institution.strip()}")
        elif isinstance(op, AddContactLinkOperation):
            title = (op.link.title or "").strip() or "Link"
            lines.append(f"Add contact link: {title}")
        elif isinstance(op, SetSkillsOperation):
            names = [s.strip() for s in op.skill_names if s.strip()]
            preview_names = ", ".join(names[:5])
            if len(names) > 5:
                preview_names += f", +{len(names) - 5} more"
            lines.append(f"Set skills: {preview_names}")
    return "\n".join(lines) if lines else "No profile changes proposed."


def list_proposals(
    session: Session,
    user_id: uuid.UUID,
    *,
    variant_id: uuid.UUID | None = None,
    status: str = "pending",
) -> ResumeProposalListResponse:
    repo = ResumeProposalRepository(session)
    rows = repo.list_by_status(user_id, status)
    if variant_id is not None:
        rows = [row for row in rows if row.variant_id == variant_id]
    return ResumeProposalListResponse(proposals=[_proposal_response(row) for row in rows])


def _experience_for_profile(
    session: Session, profile: Profile, experience_id: uuid.UUID
) -> ProfileExperience | None:
    row = session.get(ProfileExperience, experience_id)
    if row is None or row.profile_id != profile.id:
        return None
    return row


def _education_for_profile(
    session: Session, profile: Profile, education_id: uuid.UUID
) -> ProfileEducation | None:
    row = session.get(ProfileEducation, education_id)
    if row is None or row.profile_id != profile.id:
        return None
    return row


def _next_experience_order(session: Session, profile_id: uuid.UUID) -> int:
    current = session.scalar(
        select(func.max(ProfileExperience.sort_order)).where(
            ProfileExperience.profile_id == profile_id
        )
    )
    return int(current or 0) + 1


def _next_education_order(session: Session, profile_id: uuid.UUID) -> int:
    current = session.scalar(
        select(func.max(ProfileEducation.sort_order)).where(
            ProfileEducation.profile_id == profile_id
        )
    )
    return int(current or 0) + 1


def _apply_operation(
    session: Session,
    profile: Profile,
    op: ResumeProposalOperation,
    *,
    user_id: uuid.UUID,
) -> None:
    if isinstance(op, SetIdentityOperation):
        set_identity_dict(profile, op.identity.model_dump())
        return

    if isinstance(op, SetSummaryOperation):
        profile.summary = op.summary.strip()
        return

    if isinstance(op, SetHeadlineOperation):
        profile.headline = op.headline.strip()[:512]
        return

    if isinstance(op, AddExperienceOperation):
        count = session.scalar(
            select(func.count())
            .select_from(ProfileExperience)
            .where(ProfileExperience.profile_id == profile.id)
        )
        if int(count or 0) >= _MAX_EXPERIENCES:
            raise ValueError("Maximum 12 experiences allowed")
        row = op.experience
        company = (
            get_or_create_company(session, row.company_name)
            if row.company_name.strip()
            else None
        )
        exp = ProfileExperience(
            profile_id=profile.id,
            company_id=company.id if company else None,
            company_name=row.company_name.strip()[:512],
            title=row.title.strip()[:512],
            location=row.location.strip()[:512] or None,
            start_date=row.start_date.strip()[:32] or None,
            end_date=row.end_date.strip()[:32] or None,
            is_current=row.is_current,
            highlights=normalize_highlights(list(row.highlights or [])),
            sort_order=_next_experience_order(session, profile.id),
        )
        session.add(exp)
        session.flush()
        return

    if isinstance(op, UpdateExperienceOperation):
        experience = _experience_for_profile(session, profile, op.experience_id)
        if experience is None:
            raise ValueError("Experience not found")
        row = op.experience
        company = (
            get_or_create_company(session, row.company_name)
            if row.company_name.strip()
            else None
        )
        experience.company_id = company.id if company else None
        experience.company_name = row.company_name.strip()[:512]
        experience.title = row.title.strip()[:512]
        experience.location = row.location.strip()[:512] or None
        experience.start_date = row.start_date.strip()[:32] or None
        experience.end_date = row.end_date.strip()[:32] or None
        experience.is_current = row.is_current
        experience.highlights = normalize_highlights(list(row.highlights or []))
        session.flush()
        return

    if isinstance(op, AppendHighlightsOperation):
        experience = _experience_for_profile(session, profile, op.experience_id)
        if experience is None:
            raise ValueError("Experience not found")
        merged = normalize_highlights(list(experience.highlights or []) + list(op.highlights))
        if len(merged) > 12:
            raise ValueError("Maximum 12 highlights per experience")
        experience.highlights = merged
        session.flush()
        return

    if isinstance(op, ReplaceHighlightsOperation):
        experience = _experience_for_profile(session, profile, op.experience_id)
        if experience is None:
            raise ValueError("Experience not found")
        experience.highlights = normalize_highlights(list(op.highlights))
        session.flush()
        return

    if isinstance(op, RemoveExperienceOperation):
        experience = _experience_for_profile(session, profile, op.experience_id)
        if experience is None:
            raise ValueError("Experience not found")
        session.delete(experience)
        session.flush()
        return

    if isinstance(op, AddEducationOperation):
        count = session.scalar(
            select(func.count())
            .select_from(ProfileEducation)
            .where(ProfileEducation.profile_id == profile.id)
        )
        if int(count or 0) >= _MAX_EDUCATION:
            raise ValueError("Maximum 8 education entries allowed")
        edu_row = op.education
        edu = ProfileEducation(
            profile_id=profile.id,
            institution=edu_row.institution.strip()[:512],
            degree=edu_row.degree.strip()[:128] or None,
            field=edu_row.field.strip()[:256] or None,
            end_date=edu_row.end_date.strip()[:32] or None,
            sort_order=_next_education_order(session, profile.id),
        )
        session.add(edu)
        session.flush()
        return

    if isinstance(op, UpdateEducationOperation):
        education = _education_for_profile(session, profile, op.education_id)
        if education is None:
            raise ValueError("Education not found")
        edu_row = op.education
        education.institution = edu_row.institution.strip()[:512]
        education.degree = edu_row.degree.strip()[:128] or None
        education.field = edu_row.field.strip()[:256] or None
        education.end_date = edu_row.end_date.strip()[:32] or None
        session.flush()
        return

    if isinstance(op, AddContactLinkOperation):
        identity = get_identity_dict(profile)
        links = list(identity.get("links") or [])
        link = op.link
        links.append({"title": link.title.strip(), "url": link.url.strip()})
        if len(links) > 12:
            raise ValueError("Maximum 12 contact links allowed")
        identity["links"] = links[:12]
        set_identity_dict(profile, identity)
        return

    if isinstance(op, SetSkillsOperation):
        names = [name.strip() for name in op.skill_names if name.strip()]
        skills = resolve_skill_names(session, names, created_by_user_id=user_id)
        replace_profile_skills(session, profile, skills)
        profile.skills = names[:50] or None
        session.flush()
        return


def apply(session: Session, user_id: uuid.UUID, proposal_id: uuid.UUID) -> ResumeProposalApplyResponse:
    repo = ResumeProposalRepository(session)
    proposal = repo.get_proposal(user_id, proposal_id)
    if proposal is None:
        raise ValueError("Proposal not found")
    if proposal.status != ResumeProposalStatus.pending.value:
        raise ValueError("Proposal is not pending")

    profile_repo = ProfileRepository(session)
    profile = profile_repo.get_or_create_profile(user_id)
    operations = validate_operations(list(proposal.operations or []))

    for op in operations:
        _apply_operation(session, profile, op, user_id=user_id)

    experiences = list_profile_experiences(session, profile.id)
    experience_titles = [row.title for row in experiences]
    embedding = embed_profile(profile, experience_titles=experience_titles)
    if embedding:
        profile.taste_embedding = embedding
    profile.updated_at = datetime.now(UTC)

    EventsRepository(session).append(
        EventType.PROFILE_UPDATED,
        user_id=user_id,
        entity_id=profile.id,
        payload={"step": "resume_builder_proposal", "proposal_id": str(proposal_id)},
    )

    repo.mark_applied(proposal)
    session.commit()

    return ResumeProposalApplyResponse(
        proposal=_proposal_response(proposal),
        message="Proposal applied to profile.",
    )


def reject(session: Session, user_id: uuid.UUID, proposal_id: uuid.UUID) -> ResumeProposalResponse:
    repo = ResumeProposalRepository(session)
    proposal = repo.get_proposal(user_id, proposal_id)
    if proposal is None:
        raise ValueError("Proposal not found")
    if proposal.status != ResumeProposalStatus.pending.value:
        raise ValueError("Proposal is not pending")
    repo.mark_rejected(proposal)
    session.commit()
    return _proposal_response(proposal)


def proposal_payload_to_operations(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert LLM proposal JSON into validated operation dicts."""
    operations: list[dict[str, Any]] = []
    summary = payload.get("summary")
    if isinstance(summary, str) and summary.strip():
        operations.append({"type": "set_summary", "summary": summary.strip()})

    roles = payload.get("roles") or []
    if isinstance(roles, list):
        for item in roles:
            if not isinstance(item, dict):
                continue
            highlights = item.get("highlights") or []
            if not isinstance(highlights, list):
                highlights = []
            experience = {
                "title": str(item.get("title") or item.get("job_title") or "").strip(),
                "company_name": str(
                    item.get("company_name") or item.get("employer") or ""
                ).strip(),
                "location": str(item.get("location") or "").strip(),
                "start_date": str(item.get("start_date") or "").strip(),
                "end_date": str(item.get("end_date") or "").strip(),
                "is_current": bool(item.get("is_current")),
                "highlights": [str(h).strip() for h in highlights if str(h).strip()],
            }
            exp_id = item.get("experience_id")
            if exp_id:
                operations.append(
                    {
                        "type": "update_experience",
                        "experience_id": str(exp_id),
                        "experience": experience,
                    }
                )
            elif experience["title"] or experience["company_name"]:
                operations.append({"type": "add_experience", "experience": experience})

    education_rows = payload.get("education") or []
    if isinstance(education_rows, list):
        for item in education_rows:
            if not isinstance(item, dict):
                continue
            edu = {
                "institution": str(item.get("institution") or "").strip(),
                "degree": str(item.get("degree") or "").strip(),
                "field": str(item.get("field") or "").strip(),
                "end_date": str(item.get("end_date") or "").strip(),
            }
            if edu["institution"]:
                operations.append({"type": "add_education", "education": edu})

    links = payload.get("links") or []
    if isinstance(links, list):
        for item in links:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            title = str(item.get("title") or item.get("label") or "Link").strip()
            operations.append(
                {
                    "type": "add_contact_link",
                    "link": {"title": title, "url": url},
                }
            )

    return operations


def create_from_builder_payload(
    session: Session,
    user_id: uuid.UUID,
    variant_id: uuid.UUID,
    payload: dict[str, Any],
    message_id: uuid.UUID,
) -> ResumeProposalResponse:
    operations = proposal_payload_to_operations(payload)
    if not operations:
        raise ValueError("Proposal contained no profile changes")
    validated = validate_operations(operations)
    repo = ResumeProposalRepository(session)
    row = repo.create(
        user_id,
        proposal_type="profile_update",
        operations=[op.model_dump(mode="json") for op in validated],
        preview_summary=preview(operations),
        variant_id=variant_id,
        message_id=message_id,
    )
    msg_repo = ResumeMessageRepository(session)
    msg_repo.update_message(message_id, proposal_id=row.id)
    session.commit()
    session.refresh(row)
    return _proposal_response(row)
