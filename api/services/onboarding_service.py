"""Onboarding service — DB-backed profile and hard constraints."""

from __future__ import annotations

from uuid import UUID

from core.deck_bootstrap import ensure_corpus_ingest, open_job_count
from core.models import EventType, ProfileEducation, ProfileExperience, ProfileSkill, Skill, User
from core.profile_embed import embed_profile
from core.skill_directory import resolve_skill_names
from core.stated_preferences import stated_facet_weights_from_questionnaire
from sqlalchemy import select
from sqlalchemy.orm import Session
from workers.consumer import enqueue_job

from api.auth import new_uuid
from api.repositories.events_repo import EventsRepository
from api.repositories.profile_repo import ProfileRepository, _education_out, _experience_out, _openness_from_legacy
from api.resume_io import extract_resume_text, save_resume_file, sniff_resume_content_type
from api.resume_parse import parse_resume_with_fallback
from api.schemas import (
    EducationIn,
    ExperienceIn,
    ProfileConfirmResponse,
    ProfileFact,
    ProfileIdentity,
    QuestionnaireRequest,
    QuestionnaireResponse,
    ResumeUploadResponse,
    SkillOut,
)

MAX_RESUME_BYTES = 5 * 1024 * 1024
ALLOWED_RESUME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _skill_out(skill: Skill) -> SkillOut:
    return SkillOut(
        id=skill.id,
        name=skill.name,
        normalized_name=skill.normalized_name,
        use_count=skill.use_count,
    )


class OnboardingService:
    def is_complete(self, session: Session, user_id: UUID) -> bool:
        return ProfileRepository(session).is_onboarding_complete(user_id)

    def save_profile(
        self,
        session: Session,
        user_id: UUID,
        facts: list[ProfileFact],
        *,
        skill_ids: list[UUID] | None = None,
        experiences: list[ExperienceIn] | None = None,
        education: list[EducationIn] | None = None,
        identity: ProfileIdentity | None = None,
    ) -> ProfileConfirmResponse:
        from core.profile_identity import resolve_identity, set_identity_dict

        repo = ProfileRepository(session)
        profile = repo.save_confirmed_facts(
            user_id,
            facts,
            skill_ids=skill_ids,
            experiences=experiences,
            education=education,
        )
        if identity is not None:
            set_identity_dict(profile, identity.model_dump())
        linked = list(
            session.scalars(
                select(Skill).join(ProfileSkill).where(ProfileSkill.profile_id == profile.id)
            )
        )
        saved_experiences = list(
            session.scalars(
                select(ProfileExperience)
                .where(ProfileExperience.profile_id == profile.id)
                .order_by(ProfileExperience.sort_order)
            )
        )
        saved_education = list(
            session.scalars(
                select(ProfileEducation)
                .where(ProfileEducation.profile_id == profile.id)
                .order_by(ProfileEducation.sort_order)
            )
        )
        EventsRepository(session).append(
            EventType.PROFILE_UPDATED,
            user_id=user_id,
            entity_id=profile.id,
            payload={"step": "profile_confirm"},
        )
        session.commit()
        return ProfileConfirmResponse(
            profile_id=profile.id,
            facts=facts,
            skills=[_skill_out(skill) for skill in linked],
            experiences=[_experience_out(row) for row in saved_experiences],
            education=[_education_out(row) for row in saved_education],
            identity=ProfileIdentity.model_validate(resolve_identity(profile)),
        )

    def save_questionnaire(
        self, session: Session, user_id: UUID, data: QuestionnaireRequest
    ) -> QuestionnaireResponse:
        repo = ProfileRepository(session)
        profile, new_terms = repo.save_questionnaire(user_id, data)

        experience_titles = list(
            session.scalars(
                select(ProfileExperience.title)
                .where(ProfileExperience.profile_id == profile.id)
                .order_by(ProfileExperience.sort_order)
            )
        )
        prior_embedding = embed_profile(profile, experience_titles=experience_titles)
        if prior_embedding:
            profile.taste_embedding = prior_embedding

        weights_row = repo.get_or_create_preference_weights(user_id)
        stated = stated_facet_weights_from_questionnaire(
            target_titles=data.target_titles,
            remote_preference=data.remote_preference,
            remote_openness=data.remote_openness or _openness_from_legacy(data.remote_preference),
            industries_to_avoid=data.industries_to_avoid,
        )
        stored = dict(weights_row.weights or {})
        stored["stated_facet_weights"] = stated
        if prior_embedding:
            stored["profile_prior_embedding"] = prior_embedding
        weights_row.weights = stored

        EventsRepository(session).append(
            EventType.PROFILE_UPDATED,
            user_id=user_id,
            entity_id=profile.id,
            payload={"step": "questionnaire"},
        )
        user = session.get(User, user_id)
        if user is not None and data.timezone:
            user.timezone = data.timezone.strip()
        if user is not None and data.referral_code:
            from contextlib import suppress

            from api.services.revenue_service import referral_service

            with suppress(LookupError, ValueError):
                referral_service.apply_code(session, user_id, data.referral_code)
        if user is not None:
            from api.services.engagement_service import engagement_service

            engagement_service.start_pro_trial(session, user)
            engagement_service.heartbeat(session, user_id, "session")
        if new_terms:
            profile.awaiting_deck_backfill = True
            enqueue_job(
                session,
                "term_ingest",
                {"terms": new_terms, "user_id": str(user_id)},
                priority=8,
            )
        else:
            enqueue_job(session, "queue_backfill", {"user_id": str(user_id)}, priority=5)
            if open_job_count(session) == 0:
                profile.awaiting_deck_backfill = True
                ensure_corpus_ingest(session, enqueue=enqueue_job)
        session.commit()
        return QuestionnaireResponse(user_id=user_id, onboarding_complete=True)

    def handle_resume_upload(
        self,
        session: Session,
        user_id: UUID,
        filename: str,
        content_type: str,
        size: int,
        data: bytes,
    ) -> ResumeUploadResponse:
        if size > MAX_RESUME_BYTES:
            raise ValueError("Resume exceeds 5MB limit")
        content_type = sniff_resume_content_type(content_type, filename, data)
        if content_type not in ALLOWED_RESUME_TYPES:
            raise ValueError("Resume must be PDF or DOCX")

        save_resume_file(user_id, filename, data)
        text = extract_resume_text(content_type, data, filename=filename)
        parsed = parse_resume_with_fallback(text, filename=filename)
        resolved = resolve_skill_names(session, parsed.skill_names, created_by_user_id=user_id)
        parsed.skills = [_skill_out(skill) for skill in resolved]

        parsed_resume = ProfileRepository(session).save_parsed_resume(
            user_id,
            facts=parsed.facts,
            raw_summary=parsed.raw_summary,
        )
        if parsed.scraped_identity is not None:
            from core.profile_identity import merge_scraped_identity

            merge_scraped_identity(parsed_resume, parsed.scraped_identity.model_dump())
        parsed_resume.parsed_resume = {
            **(parsed_resume.parsed_resume or {}),
            "resume_filename": filename,
            "resume_size_bytes": size,
        }
        EventsRepository(session).append(
            EventType.PROFILE_UPDATED,
            user_id=user_id,
            entity_id=parsed_resume.id,
            payload={"step": "resume_upload", "filename": filename},
        )
        session.commit()
        return ResumeUploadResponse(
            upload_id=new_uuid(),
            filename=filename,
            size_bytes=size,
            parsed_profile=parsed,
        )


onboarding_service = OnboardingService()

handle_resume_upload = onboarding_service.handle_resume_upload
