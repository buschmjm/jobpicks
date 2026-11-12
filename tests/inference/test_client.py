"""Tests for the OpenAI-compatible inference client."""

from __future__ import annotations

import httpx
import pytest
import respx
from inference.client import (
    CircuitBreaker,
    CircuitState,
    InferenceClient,
    InferenceUnavailableError,
)


@respx.mock
def test_chat_completion_success(inference_client: InferenceClient) -> None:
    route = respx.post("http://ollama.test/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"ok": true}'}}],
            },
        )
    )

    content = inference_client.chat_completion(
        model="qwen2.5:7b-instruct",
        messages=[{"role": "user", "content": "hi"}],
    )

    assert content == '{"ok": true}'
    assert route.called
    assert inference_client.circuit_breaker.state == CircuitState.CLOSED


@respx.mock
def test_chat_completion_stream_yields_deltas(inference_client: InferenceClient) -> None:
    body = (
        b'data: {"choices":[{"delta":{"content":"Hel"}}]}\n\n'
        b'data: {"choices":[{"delta":{"content":"lo"}}]}\n\n'
        b"data: [DONE]\n\n"
    )
    respx.post("http://ollama.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})
    )

    chunks = list(
        inference_client.chat_completion_stream(
            model="qwen3:8b",
            messages=[{"role": "user", "content": "hi"}],
        )
    )

    assert chunks == ["Hel", "lo"]


@respx.mock
def test_chat_completion_retries_then_succeeds(inference_client: InferenceClient) -> None:
    route = respx.post("http://ollama.test/v1/chat/completions").mock(
        side_effect=[
            httpx.Response(503, json={"error": "busy"}),
            httpx.Response(
                200,
                json={"choices": [{"message": {"content": "done"}}]},
            ),
        ]
    )

    content = inference_client.chat_completion(
        model="qwen2.5:7b-instruct",
        messages=[{"role": "user", "content": "hi"}],
    )

    assert content == "done"
    assert route.call_count == 2


@respx.mock
def test_chat_completion_fails_after_retries(inference_client: InferenceClient) -> None:
    respx.post("http://ollama.test/v1/chat/completions").mock(
        return_value=httpx.Response(503, json={"error": "busy"}),
    )

    with pytest.raises(InferenceUnavailableError):
        inference_client.chat_completion(
            model="qwen2.5:7b-instruct",
            messages=[{"role": "user", "content": "hi"}],
        )


def test_circuit_breaker_opens_and_recovers() -> None:
    breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=0.01)

    assert breaker.allow_request()
    breaker.record_failure()
    assert breaker.allow_request()
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN
    assert not breaker.allow_request()

    import time

    time.sleep(0.02)
    assert breaker.allow_request()
    assert breaker.state == CircuitState.HALF_OPEN

    breaker.record_success()
    assert breaker.state == CircuitState.CLOSED


@respx.mock
def test_embeddings_endpoint(inference_client: InferenceClient) -> None:
    respx.post("http://ollama.test/v1/embeddings").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"index": 0, "embedding": [0.1, 0.2, 0.3]},
                    {"index": 1, "embedding": [0.4, 0.5, 0.6]},
                ]
            },
        )
    )

    vectors = inference_client.embeddings(model="nomic-embed-text", input_text=["a", "b"])
    assert vectors == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]


@respx.mock
def test_open_circuit_blocks_requests(inference_client: InferenceClient) -> None:
    inference_client.circuit_breaker.state = CircuitState.OPEN
    inference_client.circuit_breaker.opened_at = __import__("time").monotonic()

    with pytest.raises(InferenceUnavailableError, match="circuit is open"):
        inference_client.chat_completion(
            model="qwen2.5:7b-instruct",
            messages=[{"role": "user", "content": "hi"}],
        )
