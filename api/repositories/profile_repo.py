"""Profile, hard constraints, and preference weight persistence."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from core.geo.geocode import GeocodeResult, geocode_us_address
from core.models import HardConstraints, PreferenceWeights, Profile, ProfileEducation, ProfileExperience, Skill
from core.profile_resume import replace_profile_education, replace_profile_experiences
from core.search_terms import register_terms
from core.seniority import seniority_to_int
from core.skill_directory import replace_profile_skills, resolve_skill_names
from core.stated_preferences import remote_acceptability_from_openness
from core.title_embedding_cache import invalidate_title_embeddings
from core.types import RemoteOpenness
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.schemas import (
    EducationIn,
    EducationOut,
    ExperienceIn,
    ExperienceOut,
    PreferencesUpdateRequest,
    ProfileFact,
    QuestionnaireRequest,
)


def _experience_out(row: ProfileExperience) -> ExperienceOut:
    return ExperienceOut(
        id=row.id,
        title=row.title,
        company_name=row.company_name,
        location=row.location or "",
        start_date=row.start_date or "",
        end_date=row.end_date or "",
        is_current=row.is_current,
        highlights=list(row.highlights or []),
    )


def _education_out(row: ProfileEducation) -> EducationOut:
    return EducationOut(
        id=row.id,
        institution=row.institution,
        degree=row.degree or "",
        field=row.field or "",
        end_date=row.end_date or "",
    )


class ProfileRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_profile(self, user_id: uuid.UUID) -> Profile | None:
        return self._session.scalar(select(Profile).where(Profile.user_id == user_id))

    def get_or_create_profile(self, user_id: uuid.UUID) -> Profile:
        profile = self.get_profile(user_id)
        if profile is not None:
            return profile
        profile = Profile(user_id=user_id, parsed_resume={"facts": []})
        self._session.add(profile)
        self._session.flush()
        return profile

    def get_or_create_hard_constraints(self, user_id: uuid.UUID) -> HardConstraints:
        row = self._session.scalar(
            select(HardConstraints).where(HardConstraints.user_id == user_id)
        )
        if row is not None:
            return row
        row = HardConstraints(user_id=user_id)
        self._session.add(row)
        self._session.flush()
        return row

    def is_onboarding_complete(self, user_id: uuid.UUID) -> bool:
        profile = self.get_profile(user_id)
        return profile is not None and profile.onboarding_completed_at is not None

    def save_parsed_resume(
        self,
        user_id: uuid.UUID,
        *,
        facts: list[ProfileFact],
        raw_summary: str | None = None,
        skill_ids: list[uuid.UUID] | None = None,
        skill_names: list[str] | None = None,
        created_by_user_id: uuid.UUID | None = None,
    ) -> Profile:
        profile = self.get_or_create_profile(user_id)
        previous = profile.parsed_resume if isinstance(profile.parsed_resume, dict) else {}
        identity = previous.get("identity") if isinstance(previous.get("identity"), dict) else {}
        profile.parsed_resume = {
            "facts": [fact.model_dump() for fact in facts],
            "raw_summary": raw_summary,
            "identity": identity,
        }
        self._apply_facts_to_columns(profile, facts)
        self._sync_directory_skills(
            profile,
            skill_ids=skill_ids,
            skill_names=skill_names,
            created_by_user_id=created_by_user_id or user_id,
        )
        self._session.flush()
        return profile

    def save_confirmed_facts(
        self,
        user_id: uuid.UUID,
        facts: list[ProfileFact],
        *,
        skill_ids: list[uuid.UUID] | None = None,
        experiences: list[ExperienceIn] | None = None,
        education: list[EducationIn] | None = None,
    ) -> Profile:
        profile = self.save_parsed_resume(user_id, facts=facts, skill_ids=skill_ids)
        if experiences is not None:
            replace_profile_experiences(self._session, profile, experiences)
        if education is not None:
            replace_profile_education(self._session, profile, education)
        self._session.flush()
        return profile

    def _sync_directory_skills(
        self,
        profile: Profile,
        *,
        skill_ids: list[uuid.UUID] | None,
        skill_names: list[str] | None,
        created_by_user_id: uuid.UUID,
    ) -> list[Skill]:
        skills: list[Skill] = []
        if skill_ids is not None:
            for skill_id in skill_ids:
                row = self._session.get(Skill, skill_id)
                if row is not None:
                    skills.append(row)
        elif skill_names:
            skills = resolve_skill_names(
                self._session, skill_names, created_by_user_id=created_by_user_id
            )
        else:
            return []
        return replace_profile_skills(self._session, profile, skills)

    def apply_location_preferences(
        self,
        user_id: uuid.UUID,
        *,
        home_location: str | None,
        max_commute_minutes: int | None,
        remote_openness: str,
        home_lat: float | None = None,
        home_lon: float | None = None,
    ) -> GeocodeResult | None:
        profile = self.get_or_create_profile(user_id)
        constraints = self.get_or_create_hard_constraints(user_id)

        openness = RemoteOpenness(remote_openness)
        constraints.remote_openness = openness.value
        constraints.remote_acceptability = remote_acceptability_from_openness(openness)
        profile.remote_preference = _legacy_remote_preference(openness)

        if openness == RemoteOpenness.REMOTE_ONLY:
            constraints.max_commute_minutes = None
        else:
            constraints.max_commute_minutes = max_commute_minutes or 45

        geocoded: GeocodeResult | None = None
        if home_location and home_location.strip():
            if home_lat is not None and home_lon is not None:
                geocoded = GeocodeResult(
                    lat=home_lat,
                    lon=home_lon,
                    formatted_name=home_location.strip(),
                    source="google_places",
                )
            else:
                geocoded = geocode_us_address(self._session, home_location.strip())
            if geocoded is not None:
                location_doc = {
                    "name": geocoded.formatted_name,
                    "lat": geocoded.lat,
                    "lon": geocoded.lon,
                    "geocoded_at": datetime.now(tz=UTC).isoformat(),
                    "source": geocoded.source,
                }
                profile.locations = [location_doc]
                constraints.locations = [location_doc]
            else:
                profile.locations = [home_location.strip()]
                constraints.locations = [{"name": home_location.strip()}]

        self._session.flush()
        return geocoded

    def save_preferences(self, user_id: uuid.UUID, data: PreferencesUpdateRequest) -> tuple[Profile, list[str]]:
        profile = self.get_or_create_profile(user_id)
        self.apply_location_preferences(
            user_id,
            home_location=data.home_location,
            max_commute_minutes=data.max_commute_minutes,
            remote_openness=data.remote_openness,
            home_lat=data.home_lat,
            home_lon=data.home_lon,
        )
        new_terms: list[str] = []
        if data.target_titles is not None:
            prior_titles = list(profile.target_titles or [])
            profile.target_titles = data.target_titles or None
            new_titles = data.target_titles or []
            removed = {t for t in prior_titles if t not in new_titles}
            if removed:
                invalidate_title_embeddings(self._session, list(removed))
            new_terms = register_terms(self._session, user_id, data.target_titles)
        if data.min_salary is not None:
            constraints = self.get_or_create_hard_constraints(user_id)
            constraints.min_salary = data.min_salary
        if data.free_text_goals is not None:
            profile.free_text_wants = data.free_text_goals
        self._session.flush()
        return profile, new_terms

    def save_questionnaire(self, user_id: uuid.UUID, data: QuestionnaireRequest) -> tuple[Profile, list[str]]:
        profile = self.get_or_create_profile(user_id)
        constraints = self.get_or_create_hard_constraints(user_id)

        prior_titles = list(profile.target_titles or [])
        profile.target_titles = data.target_titles or None
        new_titles = data.target_titles or []
        removed = {t for t in prior_titles if t not in new_titles}
        if removed:
            invalidate_title_embeddings(self._session, list(removed))
        profile.free_text_wants = data.free_text_goals
        profile.onboarding_completed_at = datetime.now(UTC)

        constraints.min_salary = data.min_salary
        constraints.never_industries = data.industries_to_avoid or None

        home = data.home_location or (data.locations[0] if data.locations else None)
        openness = data.remote_openness or _openness_from_legacy(data.remote_preference)
        commute = data.max_commute_minutes if data.max_commute_minutes is not None else data.location_radius_miles
        self.apply_location_preferences(
            user_id,
            home_location=home,
            max_commute_minutes=commute,
            remote_openness=openness,
            home_lat=data.home_lat,
            home_lon=data.home_lon,
        )

        new_terms = register_terms(self._session, user_id, data.target_titles)
        self._session.flush()
        return profile, new_terms

    def get_current_preference_weights(self, user_id: uuid.UUID) -> PreferenceWeights | None:
        return self._session.scalar(
            select(PreferenceWeights)
            .where(PreferenceWeights.user_id == user_id)
            .where(PreferenceWeights.is_current.is_(True))
        )

    def get_or_create_preference_weights(self, user_id: uuid.UUID) -> PreferenceWeights:
        current = self.get_current_preference_weights(user_id)
        if current is not None:
            return current
        row = PreferenceWeights(user_id=user_id, version=1, is_current=True, weights={})
        self._session.add(row)
        self._session.flush()
        return row

    def save_preference_state(
        self,
        user_id: uuid.UUID,
        *,
        weights: dict[str, Any],
        facet_boosts: dict[str, Any] | None,
        taste_embedding: list[float] | None,
        right_swipe_count: int,
    ) -> PreferenceWeights:
        current = self.get_or_create_preference_weights(user_id)
        current.weights = weights
        current.facet_boosts = facet_boosts
        current.taste_embedding = taste_embedding
        current.right_swipe_count = right_swipe_count
        profile = self.get_or_create_profile(user_id)
        if taste_embedding is not None:
            profile.taste_embedding = taste_embedding
        self._session.flush()
        return current

    @staticmethod
    def _apply_facts_to_columns(profile: Profile, facts: list[ProfileFact]) -> None:
        for fact in facts:
            key = fact.key.lower()
            if key in {"title", "headline", "target_title"}:
                profile.headline = fact.value
            elif key == "summary":
                profile.summary = fact.value
            elif key == "years_experience":
                try:
                    profile.years_experience = float(str(fact.value).strip())
                except (TypeError, ValueError):
                    continue
            elif key == "seniority_level":
                profile.seniority_level = fact.value
                profile.seniority_int = seniority_to_int(fact.value)
            elif key in {"primary_stack", "skills", "stack"}:
                continue
            elif key == "location":
                profile.locations = [fact.value]


def _legacy_remote_preference(openness: RemoteOpenness) -> str:
    if openness == RemoteOpenness.REMOTE_ONLY:
        return "remote"
    if openness == RemoteOpenness.LOCAL_ONLY:
        return "onsite"
    return "any"


def _openness_from_legacy(preference: str) -> str:
    mapping = {
        "remote": RemoteOpenness.REMOTE_ONLY.value,
        "hybrid": RemoteOpenness.OPEN_TO_REMOTE.value,
        "onsite": RemoteOpenness.LOCAL_ONLY.value,
        "any": RemoteOpenness.OPEN_TO_REMOTE.value,
    }
    return mapping.get(preference, RemoteOpenness.OPEN_TO_REMOTE.value)
