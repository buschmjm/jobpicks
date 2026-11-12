"""Tests for resume document builder and tailor heuristics."""

from __future__ import annotations

from api.repositories.profile_repo import ProfileRepository
from api.repositories.user_repo import UserRepository
from api.schemas import ExperienceIn, FactStatus, ProfileFact
from core.resume.document import (
    RESUME_SCHEMA,
    apply_tailor_selection,
    build_master_document,
    heuristic_tailor_selection,
)
from core.resume.render import render_ats_html
from sqlalchemy.orm import Session


def test_build_master_and_render(db_session: Session) -> None:
    user = UserRepository(db_session).get_or_create_by_email("resume-builder@example.com")
    db_session.commit()
    ProfileRepository(db_session).save_confirmed_facts(
        user.id,
        [
            ProfileFact(key="full_name", value="Alex Example", status=FactStatus.confirmed),
        ],
        experiences=[
            ExperienceIn(
                title="Platform Engineer",
                company_name="Acme",
                location="Remote",
                start_date="2022-01",
                end_date="present",
                is_current=True,
                highlights=["Built Kubernetes release platform", "Automated CI/CD with GitHub Actions"],
            )
        ],
    )
    db_session.commit()

    doc = build_master_document(db_session, user.id, email=user.email)
    assert doc["schema"] == RESUME_SCHEMA
    assert doc["header"]["full_name"] == "Alex Example"
    assert doc["roles"][0]["highlights"][0]["included"] is True

    selection = heuristic_tailor_selection(doc, "Kubernetes platform engineer CI/CD")
    tailored = apply_tailor_selection(
        doc,
        selection,
        target={"title": "Platform Engineer", "company": "Globex"},
    )
    html = render_ats_html(tailored)
    assert "Alex Example" in html
    assert "Platform Engineer" in html
    assert "Kubernetes" in html or "CI/CD" in html
    assert "layout-ats" in html


def test_render_skill_groups_uses_items_key() -> None:
    """Jinja dict.attr for 'items' resolves to dict.items — template must use group['items']."""
    html = render_ats_html(
        {
            "header": {"full_name": "Sam Skills"},
            "summary_paragraphs": [],
            "roles": [],
            "skill_groups": [
                {
                    "label": "Languages",
                    "items": [
                        {"text": "Python", "included": True},
                        {"text": "Go", "included": True},
                        {"text": "COBOL", "included": False},
                    ],
                }
            ],
            "projects": [],
            "education": [],
            "target": {},
        }
    )
    assert "Sam Skills" in html
    assert "Python" in html
    assert "Go" in html
    assert "COBOL" not in html
    assert "Languages" in html
