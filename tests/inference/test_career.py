"""Tests for career title suggestion inference."""

from __future__ import annotations

import json

import httpx
import respx
from inference.career import (
    TitleSuggestionResult,
    suggest_job_titles,
    suggest_job_titles_llm,
    template_title_suggestions,
)
from inference.client import CircuitState, InferenceClient
from inference.extraction import ExtractionError

SNAPSHOT = {
    "headline": "Staff SRE",
    "summary": "Platform engineer with Kubernetes experience.",
    "seniority_level": "senior",
    "years_experience": 8.0,
    "skills": ["Kubernetes", "Terraform", "Python"],
    "experiences": [
        {
            "title": "Staff SRE",
            "company": "Acme Corp",
            "highlights": ["Led platform team", "Managed on-call rotation"],
        },
        {
            "title": "Site Reliability Engineer",
            "company": "Beta Inc",
            "highlights": ["Built CI/CD pipelines"],
        },
    ],
    "education": [{"institution": "State U", "degree": "B.S.", "field": "CS"}],
    "goals": "Move into platform leadership without leaving hands-on work.",
}


def test_template_title_suggestions_includes_past_titles() -> None:
    results = template_title_suggestions(SNAPSHOT)
    titles = {item.title for item in results}
    assert "Staff SRE" in titles
    assert any(item.tier == "adjacent" for item in results)


def test_template_title_suggestions_senior_variant() -> None:
    results = template_title_suggestions(SNAPSHOT)
    assert any(item.title == "Senior Site Reliability Engineer" for item in results)


@respx.mock
def test_suggest_job_titles_llm_parses_response() -> None:
    client = InferenceClient(base_url="http://ollama.test/v1")
    payload = {
        "suggestions": [
            {
                "title": "Platform Engineer",
                "tier": "qualified",
                "reason": "Strong overlap with your SRE and platform work.",
            },
            {
                "title": "Engineering Manager",
                "tier": "adjacent",
                "reason": "Your leadership highlights support a people-management path.",
            },
            {
                "title": "DevOps Engineer",
                "tier": "qualified",
                "reason": "CI/CD and infrastructure skills map directly.",
            },
        ]
    }
    respx.post("http://ollama.test/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(payload)}}]},
        )
    )

    results = suggest_job_titles_llm(SNAPSHOT, client=client)
    assert len(results) == 3
    assert results[0].tier == "qualified"
    client.close()


@respx.mock
def test_suggest_job_titles_falls_back_when_circuit_open() -> None:
    client = InferenceClient(base_url="http://ollama.test/v1")
    client.circuit_breaker.state = CircuitState.OPEN
    client.circuit_breaker.opened_at = __import__("time").monotonic()

    output = suggest_job_titles(SNAPSHOT, client=client)
    assert output.source == "template"
    assert len(output.suggestions) >= 1
    assert isinstance(output.suggestions[0], TitleSuggestionResult)
    client.close()


@respx.mock
def test_suggest_job_titles_falls_back_on_invalid_llm_payload() -> None:
    client = InferenceClient(base_url="http://ollama.test/v1")
    respx.post("http://ollama.test/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps({"suggestions": []})}}]},
        )
    )

    output = suggest_job_titles(SNAPSHOT, client=client)
    assert output.source == "template"
    client.close()


def test_suggest_job_titles_llm_rejects_too_few_items() -> None:
    client = InferenceClient(base_url="http://ollama.test/v1")
    with respx.mock:
        respx.post("http://ollama.test/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "suggestions": [
                                            {
                                                "title": "Only One",
                                                "tier": "qualified",
                                                "reason": "Single suggestion is not enough.",
                                            }
                                        ]
                                    }
                                )
                            }
                        }
                    ]
                },
            )
        )
        try:
            suggest_job_titles_llm(SNAPSHOT, client=client)
            raised = False
        except ExtractionError:
            raised = True
        assert raised
    client.close()
