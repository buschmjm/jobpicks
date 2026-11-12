"""Tests for profile snapshot builder and career API."""

from __future__ import annotations

from unittest.mock import patch

from api.main import app
from api.repositories.profile_repo import ProfileRepository
from api.repositories.user_repo import UserRepository
from api.schemas import EducationIn, ExperienceIn, FactStatus, ProfileFact
from api.services.career_service import get_title_suggestions
from core.career.profile_snapshot import (
    build_profile_snapshot,
    tenure_years_approx,
)
from fastapi.testclient import TestClient
from inference.career import TitleSuggestionResult, TitleSuggestionsOutput
from sqlalchemy.orm import Session


def _seed_profile(db_session: Session, email: str = "career@example.com"):
    user = UserRepository(db_session).get_or_create_by_email(email)
    db_session.commit()
    ProfileRepository(db_session).save_confirmed_facts(
        user.id,
        [
            ProfileFact(key="full_name", value="Jane Doe", status=FactStatus.confirmed),
            ProfileFact(key="years_experience", value="14", status=FactStatus.confirmed),
        ],
        experiences=[
            ExperienceIn(
                title="Infrastructure Engineer",
                company_name="Current Co",
                start_date="2022-01",
                end_date="present",
                is_current=True,
                highlights=["Kubernetes platform"],
            ),
            ExperienceIn(
                title="Systems Administrator",
                company_name="Earlier Co",
                start_date="2012-06",
                end_date="2021-12",
                is_current=False,
                highlights=["Windows and Linux fleets"],
            ),
        ],
        education=[
            EducationIn(
                institution="Nursing College",
                degree="BSN",
                field="Nursing",
                end_date="2018",
            )
        ],
    )
    # Persist stated total years on the profile column used by the snapshot.
    profile = ProfileRepository(db_session).get_profile(user.id)
    assert profile is not None
    profile.years_experience = 14.0
    db_session.commit()
    return user


def test_tenure_years_approx_from_dates() -> None:
    years = tenure_years_approx("2020-01", "2022-01", is_current=False)
    assert years is not None
    assert 1.9 <= years <= 2.2


def test_build_profile_snapshot_separates_totals_from_roles(db_session: Session) -> None:
    user = _seed_profile(db_session)
    snapshot = build_profile_snapshot(db_session, user.id, goals="Leadership role in nursing")
    assert snapshot["schema"] == "jobdeck.profile.v2"
    assert snapshot["career_totals"]["years_across_all_roles"] == 14.0
    assert snapshot["career_totals"]["role_count"] == 2
    assert "years_experience" not in snapshot
    assert "experiences" not in snapshot

    current = snapshot["roles"][0]
    assert current["job_title"] == "Infrastructure Engineer"
    assert current["employment"]["is_current"] is True
    assert current["employment"]["end"] == "present"
    assert current["employment"]["tenure_years_approx"] is not None
    assert current["employment"]["tenure_years_approx"] < 10

    earlier = snapshot["roles"][1]
    assert earlier["job_title"] == "Systems Administrator"
    assert earlier["employment"]["tenure_years_approx"] is not None
    assert earlier["employment"]["tenure_years_approx"] >= 9

    assert snapshot["education"][0]["degree"] == "BSN"
    assert snapshot["preferences"]["goals_override"] == "Leadership role in nursing"


def test_title_suggestions_requires_auth() -> None:
    client = TestClient(app)
    response = client.get("/api/career/title-suggestions")
    assert response.status_code == 401


def test_get_title_suggestions_service(db_session: Session) -> None:
    user = _seed_profile(db_session)
    mock_output = TitleSuggestionsOutput(
        suggestions=[
            TitleSuggestionResult(
                title="Charge Nurse",
                tier="qualified",
                reason="Natural progression from your RN experience.",
            ),
            TitleSuggestionResult(
                title="Nurse Manager",
                tier="adjacent",
                reason="Leadership path adjacent to bedside nursing.",
            ),
            TitleSuggestionResult(
                title="Clinical Nurse Leader",
                tier="adjacent",
                reason="Combines clinical expertise with coordination duties.",
            ),
        ],
        source="template",
    )
    with patch("api.services.career_service.suggest_job_titles", return_value=mock_output):
        result = get_title_suggestions(db_session, user.id, goals="nursing leadership")
    assert len(result.suggestions) == 3
    assert result.source == "template"
