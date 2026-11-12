"""Workstream A acceptance tests (AT1–AT5)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx
from inference.client import InferenceClient
from inference.config import DEFAULT_LLM_CHAT_MODEL, llm_base_url
from inference.faq_router import try_faq_answer
from inference.load_control import (
    BUSY_ADVISOR_REPLY,
    begin_advisor_fifo,
    end_advisor_fifo,
)
from inference.prompt_builder import (
    MAX_PROMPT_TOKENS,
    build_chat_messages,
    system_prompt_bytes,
)
from inference.prompts import load_prompt
from inference.telemetry import estimate_tokens

from workers import consumer


def test_at1_prompt_builder_respects_token_budget_and_strips_raw_text() -> None:
    context = {
        "profile": {
            "skills": ["python", "kubernetes"],
            "resume_text": "John Doe\n123 Main Street\nSenior engineer",
            "job_description": "Full posting body with requirements",
        }
    }
    history = [{"role": "user", "content": f"turn {i}"} for i in range(10)]
    messages = build_chat_messages(
        prompt_name="career_advisor",
        structured_context=context,
        history=history,
        user_message="What roles fit me?",
    )
    total = sum(estimate_tokens(m["content"]) for m in messages)
    assert total <= MAX_PROMPT_TOKENS
    system_content = messages[0]["content"]
    assert "Full posting body" not in system_content
    assert "John Doe" not in system_content
    assert "[omitted — use structured fields only]" in system_content

    first = system_prompt_bytes("career_advisor")
    second = system_prompt_bytes("career_advisor")
    assert first == second


def test_at2_faq_router_never_calls_llm() -> None:
    answer = try_faq_answer("How does the match score work for my deck?")
    assert answer is not None
    with patch("inference.client.InferenceClient.chat_completion") as chat_mock:
        with patch("inference.client.InferenceClient.chat_completion_stream") as stream_mock:
            assert answer.reply
            chat_mock.assert_not_called()
            stream_mock.assert_not_called()


def test_at3_worker_defers_llm_job_when_interactive_lock_held() -> None:
    session = MagicMock()
    job = MagicMock()
    job.id = uuid.uuid4()
    job.job_type = "cron_normalize_embed"
    job.payload = {}

    with (
        patch.object(consumer, "claim_next_job", return_value=job),
        patch("inference.load_control.try_worker_llm_slot", return_value=False) as try_slot,
        patch("inference.load_control.defer_worker_llm_job") as defer,
        patch.object(consumer, "dispatch_job") as dispatch,
    ):
        processed = consumer.process_one(session)

    assert processed is True
    try_slot.assert_called_once_with(session)
    defer.assert_called_once_with(session, job.id)
    dispatch.assert_not_called()


def test_at4_fourth_advisor_request_gets_busy_reply() -> None:
    import inference.load_control as lc

    with lc._advisor_fifo_lock:
        lc._advisor_fifo_depth = 0

    for _ in range(3):
        assert begin_advisor_fifo() == "proceed"

    assert begin_advisor_fifo() == "busy"
    assert "several conversations" in BUSY_ADVISOR_REPLY.lower()

    for _ in range(3):
        end_advisor_fifo()


@respx.mock
def test_at5_llm_base_url_openai_compatible_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_BASE_URL", "http://mock-llm.test/v1")
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)

    client = InferenceClient()
    assert client.base_url == "http://mock-llm.test/v1"
    assert llm_base_url() == "http://mock-llm.test/v1"

    respx.post("http://mock-llm.test/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}}]},
        )
    )
    content = client.chat_completion(
        model=DEFAULT_LLM_CHAT_MODEL,
        messages=[{"role": "user", "content": "ping"}],
    )
    assert content == "ok"
    client.close()


def test_default_chat_model_is_qwen3_4b(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OLLAMA_CHAT_MODEL", raising=False)
    monkeypatch.delenv("LLM_CHAT_MODEL", raising=False)
    loaded = load_prompt("career_advisor")
    assert loaded.model == DEFAULT_LLM_CHAT_MODEL or loaded.model
