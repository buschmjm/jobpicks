"""Tests for match explanations and template fallback."""

from __future__ import annotations

from inference.explanations import (
    MatchExplanation,
    explain_match,
    match_explanation_from_components,
    template_explanation,
)

USER_PROFILE = {
    "skills": [
        {"value": "kubernetes", "status": "confirmed"},
        {"value": "terraform", "status": "confirmed"},
        {"value": "python", "status": "confirmed"},
    ],
    "seniority_level": {"value": "senior", "status": "inferred"},
    "hard_constraints": {"min_salary": 140000, "remote_preference": "remote"},
}

JOB = {
    "title": "Senior Platform Engineer",
    "seniority_level": "senior",
    "required_skills": ["kubernetes", "terraform", "go"],
    "work_arrangement": "remote",
    "salary_min": 150000,
}


def test_template_explanation_skill_overlap() -> None:
    result = template_explanation(user_profile=USER_PROFILE, job=JOB)

    assert isinstance(result, MatchExplanation)
    assert result.source == "template"
    assert any("kubernetes" in bullet.lower() for bullet in result.why)
    assert any("go" in bullet.lower() for bullet in result.caution)


def test_template_explanation_salary_and_remote() -> None:
    result = template_explanation(user_profile=USER_PROFILE, job=JOB)

    assert any("salary" in bullet.lower() for bullet in result.why)
    assert any("remote" in bullet.lower() or "arrangement" in bullet.lower() for bullet in result.why)


def test_component_bullets_list_criteria_without_percentages() -> None:
    result = match_explanation_from_components(
        {
            "semantic": 0.82,
            "skill": 0.76,
            "title": 0.71,
            "level": 0.2,
            "comp": 0.2,
            "geo": 0.9,
        }
    )

    assert any("profile fit" in bullet.lower() for bullet in result.why)
    assert any("location fit" in bullet.lower() for bullet in result.why)
    assert all("%" not in bullet for bullet in result.why)
    assert all("%" not in bullet for bullet in result.caution)


def test_explain_match_uses_score_components_without_llm() -> None:
    components = {
        "semantic": 0.82,
        "skill": 0.76,
        "title": 0.71,
        "level": 0.68,
        "comp": 0.55,
        "geo": 0.9,
    }
    result = explain_match(user_profile=USER_PROFILE, job=JOB, score_features=components)

    assert result.source == "template"
    assert len(result.why) >= 2
    assert result == match_explanation_from_components(components)


def test_explain_match_falls_back_to_template_without_components() -> None:
    result = explain_match(user_profile=USER_PROFILE, job=JOB)

    assert result.source == "template"
    assert len(result.why) >= 1
