"""Post-onboarding resume (identity + experience + education) read/write."""

from __future__ import annotations

import uuid

from core.models import EventType, Profile, ProfileExperience
from core.profile_embed import embed_profile
from core.profile_identity import merge_scraped_identity, resolve_identity, set_identity_dict
from core.profile_resume import (
    list_profile_education,
    list_profile_experiences,
    replace_profile_education,
    replace_profile_experiences,
)
from core.skill_directory import replace_profile_skills, resolve_skill_names
from sqlalchemy.orm import Session

from api.repositories.events_repo import EventsRepository
from api.repositories.profile_repo import ProfileRepository, _education_out, _experience_out
from api.repositories.user_repo import UserRepository
from api.resume_io import extract_resume_text, save_resume_file, sniff_resume_content_type
from api.resume_parse import parse_resume_with_fallback
from api.resume_sections import normalize_highlights
from api.schemas import (
    EducationIn,
    ExperienceIn,
    ExperienceOut,
    ProfileIdentity,
    ProfileResumeResponse,
    ProfileResumeUpdateRequest,
    ProfileResumeUpdateResponse,
    ProfileResumeUploadResponse,
)
from api.services.onboarding_service import ALLOWED_RESUME_TYPES, MAX_RESUME_BYTES


def _identity_out(profile: Profile, *, account_email: str | None = None) -> ProfileIdentity:
    return ProfileIdentity.model_validate(resolve_identity(profile, account_email=account_email))


def _experience_out_normalized(row: ProfileExperience) -> ExperienceOut:
    out = _experience_out(row)
    return out.model_copy(update={"highlights": normalize_highlights(list(out.highlights or []))})


class ProfileService:
    def get_resume(self, session: Session, user_id: uuid.UUID) -> ProfileResumeResponse:
        repo = ProfileRepository(session)
        profile = repo.get_or_create_profile(user_id)
        user = UserRepository(session).get_by_id(user_id)
        account_email = user.email if user else None
        experiences = list_profile_experiences(session, profile.id)
        education = list_profile_education(session, profile.id)
        return ProfileResumeResponse(
            profile_id=profile.id,
            identity=_identity_out(profile, account_email=account_email),
            experiences=[_experience_out_normalized(row) for row in experiences],
            education=[_education_out(row) for row in education],
        )

    def update_resume(
        self,
        session: Session,
        user_id: uuid.UUID,
        data: ProfileResumeUpdateRequest,
    ) -> ProfileResumeUpdateResponse:
        repo = ProfileRepository(session)
        profile = repo.get_or_create_profile(user_id)
        user = UserRepository(session).get_by_id(user_id)
        account_email = user.email if user else None
        if data.identity is not None:
            set_identity_dict(profile, data.identity.model_dump())
        saved_experiences = replace_profile_experiences(session, profile, data.experiences)
        saved_education = replace_profile_education(session, profile, data.education)

        experience_titles = [row.title for row in saved_experiences]
        embedding = embed_profile(profile, experience_titles=experience_titles)
        if embedding:
            profile.taste_embedding = embedding

        EventsRepository(session).append(
            EventType.PROFILE_UPDATED,
            user_id=user_id,
            entity_id=profile.id,
            payload={"step": "resume_edit"},
        )
        session.commit()
        return ProfileResumeUpdateResponse(
            profile_id=profile.id,
            identity=_identity_out(profile, account_email=account_email),
            experiences=[_experience_out(row) for row in saved_experiences],
            education=[_education_out(row) for row in saved_education],
        )

    def import_resume_file(
        self,
        session: Session,
        user_id: uuid.UUID,
        *,
        filename: str,
        content_type: str,
        data: bytes,
    ) -> ProfileResumeUploadResponse:
        """Parse an uploaded PDF/DOCX and replace stored experience + education."""
        if len(data) > MAX_RESUME_BYTES:
            raise ValueError("Resume exceeds 5MB limit")
        content_type = sniff_resume_content_type(content_type, filename, data)
        if content_type not in ALLOWED_RESUME_TYPES:
            raise ValueError("Resume must be PDF or DOCX")

        save_resume_file(user_id, filename, data)
        text = extract_resume_text(content_type, data, filename=filename)
        parsed = parse_resume_with_fallback(text, filename=filename)

        repo = ProfileRepository(session)
        profile = repo.get_or_create_profile(user_id)
        # Refresh headline/summary facts when the new file has them.
        if parsed.facts:
            repo.save_parsed_resume(
                user_id,
                facts=parsed.facts,
                raw_summary=parsed.raw_summary,
                skill_names=parsed.skill_names or None,
                created_by_user_id=user_id,
            )
            profile = repo.get_or_create_profile(user_id)

        if parsed.scraped_identity is not None:
            merge_scraped_identity(profile, parsed.scraped_identity.model_dump())

        experiences = [
            ExperienceIn(
                title=exp.title,
                company_name=exp.company_name,
                location=exp.location,
                start_date=exp.start_date,
                end_date=exp.end_date,
                is_current=exp.is_current,
                highlights=list(exp.highlights or []),
            )
            for exp in (parsed.experiences or [])
        ]
        education = [
            EducationIn(
                institution=edu.institution,
                degree=edu.degree,
                field=edu.field,
                end_date=edu.end_date,
            )
            for edu in (parsed.education or [])
        ]
        saved_experiences = replace_profile_experiences(session, profile, experiences)
        saved_education = replace_profile_education(session, profile, education)

        if parsed.skill_names:
            skills = resolve_skill_names(
                session, parsed.skill_names, created_by_user_id=user_id
            )
            replace_profile_skills(session, profile, skills)

        experience_titles = [row.title for row in saved_experiences]
        embedding = embed_profile(profile, experience_titles=experience_titles)
        if embedding:
            profile.taste_embedding = embedding

        EventsRepository(session).append(
            EventType.PROFILE_UPDATED,
            user_id=user_id,
            entity_id=profile.id,
            payload={"step": "resume_reupload", "filename": filename},
        )
        session.commit()
        user = UserRepository(session).get_by_id(user_id)
        account_email = user.email if user else None
        return ProfileResumeUploadResponse(
            profile_id=profile.id,
            identity=_identity_out(profile, account_email=account_email),
            experiences=[_experience_out(row) for row in saved_experiences],
            education=[_education_out(row) for row in saved_education],
            filename=filename,
            message=(
                "Resume imported and work history replaced. "
                "Review accomplishments below, then save if you make edits."
            ),
        )


profile_service = ProfileService()
