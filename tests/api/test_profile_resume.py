"""Tests for profile resume GET/PUT API."""

from __future__ import annotations

from unittest.mock import patch

from api.main import app
from api.repositories.profile_repo import ProfileRepository
from api.repositories.user_repo import UserRepository
from api.schemas import (
    EducationIn,
    ExperienceIn,
    FactStatus,
    ProfileFact,
    ProfileIdentity,
    ProfileResumeUpdateRequest,
    ProfileWebLink,
)
from api.services.profile_service import profile_service
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def test_profile_resume_requires_auth() -> None:
    client = TestClient(app)
    assert client.get("/api/profile/resume").status_code == 401
    assert client.put("/api/profile/resume", json={"experiences": [], "education": []}).status_code == 401


def test_get_and_update_resume(db_session: Session) -> None:
    user = UserRepository(db_session).get_or_create_by_email("resume@example.com")
    db_session.commit()
    ProfileRepository(db_session).save_confirmed_facts(
        user.id,
        [ProfileFact(key="full_name", value="Riley", status=FactStatus.confirmed)],
        experiences=[
            ExperienceIn(
                title="SRE",
                company_name="Acme",
                location="Remote",
                start_date="2020-01",
                end_date="present",
                is_current=True,
                highlights=["Owned on-call", "Cut MTTR 40%"],
            )
        ],
        education=[
            EducationIn(
                institution="State U",
                degree="BS",
                field="CS",
                end_date="2019",
            )
        ],
    )
    db_session.commit()

    got = profile_service.get_resume(db_session, user.id)
    assert got.experiences[0].title == "SRE"
    assert got.experiences[0].highlights == ["Owned on-call", "Cut MTTR 40%"]
    assert got.education[0].institution == "State U"
    assert got.identity.preferred_name == "Riley"
    assert got.identity.email == "resume@example.com"

    with patch("api.services.profile_service.embed_profile", return_value=None):
        updated = profile_service.update_resume(
            db_session,
            user.id,
            ProfileResumeUpdateRequest(
                identity=ProfileIdentity(
                    preferred_name="Riley Quinn",
                    email="riley@jobs.example",
                    phone="555-010-0199",
                    pronouns="they/them/theirs",
                    show_pronouns=True,
                    links=[ProfileWebLink(title="LinkedIn", url="https://linkedin.com/in/riley")],
                ),
                experiences=[
                    ExperienceIn(
                        title="Senior SRE",
                        company_name="Acme",
                        location="Austin, TX",
                        start_date="2020-01",
                        end_date="present",
                        is_current=True,
                        highlights=["Owned on-call", "Built platform"],
                    ),
                    ExperienceIn(
                        title="Sysadmin",
                        company_name="Earlier Co",
                        start_date="2016-01",
                        end_date="2019-12",
                        is_current=False,
                        highlights=["Linux fleets"],
                    ),
                ],
                education=[
                    EducationIn(
                        institution="State U",
                        degree="BS",
                        field="Computer Science",
                        end_date="2019",
                    )
                ],
            ),
        )

    assert len(updated.experiences) == 2
    assert updated.experiences[0].title == "Senior SRE"
    assert updated.experiences[0].highlights == ["Owned on-call", "Built platform"]
    assert updated.experiences[1].highlights == ["Linux fleets"]
    assert updated.education[0].field == "Computer Science"
    assert updated.identity.preferred_name == "Riley Quinn"
    assert updated.identity.phone == "555-010-0199"
    assert updated.identity.pronouns == "they/them/theirs"
    assert updated.identity.show_pronouns is True
    assert updated.identity.links[0].title == "LinkedIn"

    again = profile_service.get_resume(db_session, user.id)
    assert again.experiences[0].title == "Senior SRE"
    assert len(again.experiences[0].highlights) == 2
    assert again.identity.email == "riley@jobs.example"
    assert again.identity.links[0].url == "https://linkedin.com/in/riley"
