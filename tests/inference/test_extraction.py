"""Tests for schema-validated extraction."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from inference.client import InferenceClient
from inference.extraction import ExtractionError, extract_job_fields, extract_resume_profile
from inference.prompts import load_prompt

VALID_RESUME = {
    "full_name": {"value": "Jane Doe", "status": "confirmed"},
    "email": {"value": "jane@example.com", "status": "confirmed"},
    "phone": {"value": "", "status": "needs_confirmation"},
    "location": {"value": "Austin, TX", "status": "inferred"},
    "summary": {"value": "Senior platform engineer.", "status": "inferred"},
    "seniority_level": {"value": "senior", "status": "inferred"},
    "years_experience": {"value": 8, "status": "inferred"},
    "skills": [
        {"value": "kubernetes", "status": "confirmed"},
        {"value": "terraform", "status": "confirmed"},
    ],
    "job_titles": [{"value": "Senior Platform Engineer", "status": "confirmed"}],
    "work_history": [
        {
            "title": {"value": "Senior Platform Engineer", "status": "confirmed"},
            "company": {"value": "Acme Corp", "status": "confirmed"},
            "start_date": {"value": "2020-01", "status": "confirmed"},
            "end_date": {"value": "present", "status": "confirmed"},
            "description": {"value": "Built k8s platform.", "status": "confirmed"},
        }
    ],
    "education": [
        {
            "degree": {"value": "BS Computer Science", "status": "confirmed"},
            "institution": {"value": "State U", "status": "confirmed"},
            "graduation_date": {"value": "2016", "status": "confirmed"},
        }
    ],
    "certifications": [{"value": "CKA", "status": "confirmed"}],
}

VALID_JOB = {
    "seniority_level": "senior",
    "job_family": "platform_engineering",
    "required_skills": ["kubernetes", "terraform"],
    "preferred_skills": ["go"],
    "work_arrangement": "remote",
    "employment_type": "full_time",
    "salary_min": 140000,
    "salary_max": 170000,
    "salary_currency": "USD",
    "years_experience_min": 5,
    "years_experience_max": None,
    "industry": "technology",
}


def _chat_route(content: str):
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": content}}]},
    )


@respx.mock
def test_extract_resume_profile_success() -> None:
    client = InferenceClient(base_url="http://ollama.test/v1")
    respx.post("http://ollama.test/v1/chat/completions").mock(
        return_value=_chat_route(json.dumps(VALID_RESUME)),
    )

    result = extract_resume_profile("Jane Doe\nSenior Platform Engineer...", client=client)

    assert result["full_name"]["value"] == "Jane Doe"
    assert result["skills"][0]["value"] == "kubernetes"
    client.close()


@respx.mock
def test_extract_resume_retries_on_invalid_json() -> None:
    client = InferenceClient(base_url="http://ollama.test/v1")
    route = respx.post("http://ollama.test/v1/chat/completions").mock(
        side_effect=[
            _chat_route("not json"),
            _chat_route(json.dumps(VALID_RESUME)),
        ]
    )

    result = extract_resume_profile("resume text", client=client)

    assert result["email"]["value"] == "jane@example.com"
    assert route.call_count == 2
    client.close()


@respx.mock
def test_extract_resume_retries_on_schema_violation() -> None:
    client = InferenceClient(base_url="http://ollama.test/v1")
    bad = dict(VALID_RESUME)
    bad.pop("education")
    route = respx.post("http://ollama.test/v1/chat/completions").mock(
        side_effect=[
            _chat_route(json.dumps(bad)),
            _chat_route(json.dumps(VALID_RESUME)),
        ]
    )

    result = extract_resume_profile("resume text", client=client)

    assert "education" in result
    assert route.call_count == 2
    client.close()


@respx.mock
def test_extract_job_fields_success() -> None:
    client = InferenceClient(base_url="http://ollama.test/v1")
    respx.post("http://ollama.test/v1/chat/completions").mock(
        return_value=_chat_route(json.dumps(VALID_JOB)),
    )

    result = extract_job_fields("Senior Platform Engineer at Acme...", client=client)

    assert result["seniority_level"] == "senior"
    assert "kubernetes" in result["required_skills"]
    client.close()


@respx.mock
def test_extract_raises_after_max_attempts() -> None:
    client = InferenceClient(base_url="http://ollama.test/v1")
    respx.post("http://ollama.test/v1/chat/completions").mock(
        return_value=_chat_route("still not json"),
    )

    with pytest.raises(ExtractionError):
        extract_resume_profile("resume", client=client, max_attempts=2)
    client.close()


@respx.mock
def test_extract_propagates_unavailable() -> None:
    client = InferenceClient(base_url="http://ollama.test/v1")
    client.circuit_breaker.state = client.circuit_breaker.state.OPEN
    client.circuit_breaker.opened_at = __import__("time").monotonic()

    with pytest.raises(ExtractionError):
        extract_job_fields("job", client=client)
    client.close()


def test_resume_prompt_mentions_protected_attributes() -> None:
    prompt = load_prompt("resume_parse")
    assert "protected attributes" in prompt.body.lower()
