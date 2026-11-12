"""Tests for career advisor inference."""

from __future__ import annotations

import json

import httpx
import respx
from inference.career_advisor import (
    AdvisorReply,
    career_advisor_reply,
    normalize_advisor_text,
    template_career_reply,
)
from inference.client import CircuitState, InferenceClient

SNAPSHOT = {
    "schema": "jobdeck.profile.v2",
    "career_totals": {
        "years_across_all_roles": 14,
        "role_count": 2,
        "note": "total across all roles",
    },
    "profile_overview": {
        "headline": "Infrastructure Engineer",
        "seniority_level": "mid",
    },
    "skills": ["Kubernetes", "Terraform"],
    "roles": [
        {
            "index": 0,
            "job_title": "Infrastructure Engineer",
            "employer": "Acme",
            "employment": {
                "start": "2022",
                "end": "present",
                "is_current": True,
                "tenure_years_approx": 2.5,
            },
            "highlights": [],
        },
        {
            "index": 1,
            "job_title": "Systems Administrator",
            "employer": "Other Co",
            "employment": {
                "start": "2010",
                "end": "2022",
                "is_current": False,
                "tenure_years_approx": 12.0,
            },
            "highlights": [],
        },
    ],
    "preferences": {
        "target_titles": ["Site Reliability Engineer"],
    },
}


def test_normalize_advisor_text_keeps_markdown() -> None:
    raw = "**Infrastructure Engineer**\n* Site Reliability Engineer\n- Platform Engineer"
    cleaned = normalize_advisor_text(raw)
    assert "**Infrastructure Engineer**" in cleaned
    assert "Site Reliability Engineer" in cleaned
    assert "Platform Engineer" in cleaned


def test_normalize_advisor_text_unwraps_fences() -> None:
    raw = "```markdown\n**Skip** this role.\n```"
    cleaned = normalize_advisor_text(raw)
    assert cleaned == "**Skip** this role."
    assert "```" not in cleaned


def test_slim_and_trim_helpers_reduce_payload() -> None:
    from inference.career_advisor import slim_advisor_snapshot, trim_advisor_history

    fat = {
        **SNAPSHOT,
        "profile_overview": {
            "headline": "Engineer",
            "summary": "x" * 900,
        },
        "preferences": {
            "target_titles": ["A"] * 20,
            "locations": [{"name": "Austin", "lat": 1.0, "lon": 2.0, "source": "x"}],
        },
    }
    slim = slim_advisor_snapshot(fat)
    assert len(str(slim["profile_overview"]["summary"])) <= 610
    assert len(slim["preferences"]["target_titles"]) == 12
    assert slim["preferences"]["locations"] == [{"name": "Austin"}]

    history = [
        {"role": "user", "content": "y" * 5000},
        {"role": "assistant", "content": "short"},
    ]
    trimmed = trim_advisor_history(history)
    assert len(trimmed) == 2
    assert len(trimmed[0]["content"]) <= 1600



def test_template_career_reply_mentions_titles() -> None:
    result = template_career_reply(SNAPSHOT, "What job titles should I search for?")
    assert isinstance(result, AdvisorReply)
    assert result.source == "template"
    assert "Site Reliability Engineer" in result.reply or "SRE" in result.reply


@respx.mock
def test_career_advisor_reply_uses_llm() -> None:
    client = InferenceClient(base_url="http://ollama.test/v1")
    payload = {"reply": "Your platform experience aligns with senior SRE and platform engineer roles."}
    respx.post("http://ollama.test/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(payload)}}]},
        )
    )

    result = career_advisor_reply(
        snapshot=SNAPSHOT,
        history=[],
        user_message="What roles fit me?",
        client=client,
    )
    assert result.source == "llm"
    assert len(result.reply) >= 20
    client.close()


@respx.mock
def test_career_advisor_reply_falls_back_when_circuit_open() -> None:
    client = InferenceClient(base_url="http://ollama.test/v1")
    client.circuit_breaker.state = CircuitState.OPEN
    client.circuit_breaker.opened_at = __import__("time").monotonic()

    result = career_advisor_reply(
        snapshot=SNAPSHOT,
        history=[],
        user_message="How do I pivot?",
        client=client,
    )
    assert result.source == "template"
    client.close()
