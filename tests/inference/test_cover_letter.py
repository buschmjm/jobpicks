"""Tests for cover letter drafting."""

from __future__ import annotations

from inference.cover_letter import draft_cover_letter, template_cover_letter

PROFILE = {
    "profile_overview": {
        "summary": (
            "Operations leader with 8 years managing office workflows, vendor relationships, "
            "and cross-functional teams."
        ),
    },
    "roles": [
        {
            "job_title": "Office Manager",
            "employer": "Northwind Logistics",
            "highlights": [
                "Reduced operating costs 18% by renegotiating vendor contracts",
                "Implemented scheduling system that cut missed appointments by 40%",
            ],
        }
    ],
    "skills": ["operations", "budgeting", "vendor management", "scheduling"],
}

IDENTITY = {"preferred_name": "Jordan Lee"}

JOB = {
    "title": "Office Manager",
    "company": "Acme Corp",
    "description": "Seeking an office manager with budgeting, vendor management, and scheduling experience.",
}


def test_template_cover_letter_uses_profile_details() -> None:
    letter = template_cover_letter(profile=PROFILE, identity=IDENTITY, job=JOB)

    assert "Office Manager" in letter
    assert "Acme Corp" in letter
    assert "vendor" in letter.lower()
    assert "Jordan Lee" in letter
    assert "I am writing to express my interest" not in letter


def test_draft_cover_letter_falls_back_without_llm(monkeypatch) -> None:
    def _boom(*_args, **_kwargs):
        raise RuntimeError("offline")

    monkeypatch.setattr("inference.cover_letter.get_client", _boom)
    letter = draft_cover_letter(profile=PROFILE, identity=IDENTITY, job=JOB)

    assert "Acme Corp" in letter
    assert len(letter) > 280
