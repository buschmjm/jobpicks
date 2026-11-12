"""Tests for Google Places home coordinates on save."""

from __future__ import annotations

from api.repositories.profile_repo import ProfileRepository
from api.repositories.user_repo import UserRepository
from api.schemas import FactStatus, ProfileFact
from sqlalchemy.orm import Session


def test_apply_location_preferences_uses_google_places_coords(db_session: Session) -> None:
    user = UserRepository(db_session).get_or_create_by_email("maps@example.com")
    db_session.commit()
    repo = ProfileRepository(db_session)
    repo.save_confirmed_facts(
        user.id,
        [ProfileFact(key="full_name", value="Jane", status=FactStatus.confirmed)],
    )
    db_session.commit()

    result = repo.apply_location_preferences(
        user.id,
        home_location="123 Main St, Austin, TX 78701, USA",
        max_commute_minutes=45,
        remote_openness="open_to_remote",
        home_lat=30.2672,
        home_lon=-97.7431,
    )
    db_session.commit()

    assert result is not None
    assert result.source == "google_places"
    assert result.lat == 30.2672

    constraints = repo.get_or_create_hard_constraints(user.id)
    assert constraints.locations is not None
    assert constraints.locations[0]["lat"] == 30.2672
    assert constraints.locations[0]["source"] == "google_places"
