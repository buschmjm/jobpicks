"""Tests for resume builder proposal validation and apply."""

from __future__ import annotations

from unittest.mock import patch

from api.repositories.profile_repo import ProfileRepository
from api.repositories.resume_proposal_repo import ResumeProposalRepository
from api.repositories.user_repo import UserRepository
from api.schemas import ExperienceIn, FactStatus, ProfileFact
from api.services.profile_service import profile_service
from api.services.resume_proposal_service import apply, preview, validate_operations
from sqlalchemy.orm import Session


def _seed_profile(db_session: Session) -> tuple:
    user = UserRepository(db_session).get_or_create_by_email("proposals@example.com")
    db_session.commit()
    ProfileRepository(db_session).save_confirmed_facts(
        user.id,
        [ProfileFact(key="full_name", value="Nova", status=FactStatus.confirmed)],
        experiences=[
            ExperienceIn(
                title="Engineer",
                company_name="Startup",
                location="Remote",
                start_date="2021-01",
                end_date="present",
                is_current=True,
                highlights=["Shipped v1"],
            )
        ],
    )
    db_session.commit()
    return user


def test_apply_add_experience(db_session: Session) -> None:
    user = _seed_profile(db_session)
    operations = [
        {
            "type": "add_experience",
            "experience": {
                "title": "Senior Engineer",
                "company_name": "BigCo",
                "location": "NYC",
                "start_date": "2024-01",
                "end_date": "",
                "is_current": True,
                "highlights": ["Led platform migration"],
            },
        }
    ]
    validated = validate_operations(operations)
    assert validated[0].type == "add_experience"

    proposal = ResumeProposalRepository(db_session).create(
        user.id,
        proposal_type="profile_update",
        operations=operations,
        preview_summary=preview(operations),
    )
    db_session.commit()

    with patch("api.services.resume_proposal_service.embed_profile", return_value=None):
        result = apply(db_session, user.id, proposal.id)

    assert result.proposal.status.value == "applied"
    resume = profile_service.get_resume(db_session, user.id)
    titles = [exp.title for exp in resume.experiences]
    assert "Senior Engineer" in titles
    bigco = next(exp for exp in resume.experiences if exp.company_name == "BigCo")
    assert bigco.highlights == ["Led platform migration"]


def test_apply_append_highlights(db_session: Session) -> None:
    user = _seed_profile(db_session)
    resume_before = profile_service.get_resume(db_session, user.id)
    experience_id = resume_before.experiences[0].id
    assert experience_id is not None

    operations = [
        {
            "type": "append_highlights",
            "experience_id": str(experience_id),
            "highlights": ["Reduced incident rate 30%"],
        }
    ]
    proposal = ResumeProposalRepository(db_session).create(
        user.id,
        proposal_type="profile_update",
        operations=operations,
        preview_summary=preview(operations),
    )
    db_session.commit()

    with patch("api.services.resume_proposal_service.embed_profile", return_value=None):
        apply(db_session, user.id, proposal.id)

    resume_after = profile_service.get_resume(db_session, user.id)
    exp = resume_after.experiences[0]
    assert "Shipped v1" in exp.highlights
    assert "Reduced incident rate 30%" in exp.highlights


def test_apply_add_contact_link(db_session: Session) -> None:
    user = _seed_profile(db_session)
    operations = [
        {
            "type": "add_contact_link",
            "link": {
                "title": "GitHub",
                "url": "https://github.com/nova-dev",
            },
        }
    ]
    proposal = ResumeProposalRepository(db_session).create(
        user.id,
        proposal_type="profile_update",
        operations=operations,
        preview_summary=preview(operations),
    )
    db_session.commit()

    with patch("api.services.resume_proposal_service.embed_profile", return_value=None):
        apply(db_session, user.id, proposal.id)

    resume = profile_service.get_resume(db_session, user.id)
    urls = [link.url for link in resume.identity.links]
    assert "https://github.com/nova-dev" in urls
