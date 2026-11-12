"""User location and commute preferences."""

from __future__ import annotations

import uuid

from core.models import HardConstraints, Profile
from core.stated_preferences import stated_facet_weights_from_questionnaire
from sqlalchemy.orm import Session
from workers.consumer import enqueue_job

from api.repositories.profile_repo import ProfileRepository
from api.schemas import PreferencesResponse, PreferencesUpdateRequest, PreferencesUpdateResponse


def _home_from_constraints(constraints: HardConstraints | None) -> tuple[str | None, float | None, float | None]:
    if not constraints or not constraints.locations:
        return None, None, None
    first = constraints.locations[0]
    if not isinstance(first, dict):
        name = str(first)
        return name, None, None
    name = first.get("name") or first.get("formatted_name")
    lat = first.get("lat")
    lon = first.get("lon")
    return (
        str(name) if name else None,
        float(lat) if lat is not None else None,
        float(lon) if lon is not None else None,
    )


def preferences_response(profile: Profile, constraints: HardConstraints | None) -> PreferencesResponse:
    home, lat, lon = _home_from_constraints(constraints)
    geocode_status: str = "missing"
    if home and lat is not None and lon is not None:
        geocode_status = "ok"
    elif home:
        geocode_status = "failed"

    openness = constraints.remote_openness if constraints and constraints.remote_openness else "open_to_remote"
    return PreferencesResponse(
        target_titles=list(profile.target_titles or []),
        min_salary=constraints.min_salary if constraints else None,
        home_location=home,
        home_lat=lat,
        home_lon=lon,
        max_commute_minutes=constraints.max_commute_minutes if constraints else None,
        remote_openness=openness,  # type: ignore[arg-type]
        free_text_goals=profile.free_text_wants,
        geocode_status=geocode_status,  # type: ignore[arg-type]
    )


class PreferencesService:
    def get(self, session: Session, user_id: uuid.UUID) -> PreferencesResponse:
        repo = ProfileRepository(session)
        profile = repo.get_or_create_profile(user_id)
        constraints = repo.get_or_create_hard_constraints(user_id)
        return preferences_response(profile, constraints)

    def update(
        self, session: Session, user_id: uuid.UUID, data: PreferencesUpdateRequest
    ) -> PreferencesUpdateResponse:
        repo = ProfileRepository(session)
        profile, new_terms = repo.save_preferences(user_id, data)
        constraints = repo.get_or_create_hard_constraints(user_id)

        weights_row = repo.get_or_create_preference_weights(user_id)
        stored = dict(weights_row.weights or {})
        stored["stated_facet_weights"] = stated_facet_weights_from_questionnaire(
            target_titles=profile.target_titles,
            remote_openness=data.remote_openness,
            industries_to_avoid=constraints.never_industries,
        )
        weights_row.weights = stored

        if new_terms:
            enqueue_job(
                session,
                "term_ingest",
                {"terms": new_terms, "user_id": str(user_id)},
                priority=8,
            )
        enqueue_job(session, "queue_backfill", {"user_id": str(user_id)}, priority=5)
        session.commit()
        return PreferencesUpdateResponse(preferences=preferences_response(profile, constraints))


preferences_service = PreferencesService()
