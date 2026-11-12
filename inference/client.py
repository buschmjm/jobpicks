"""OpenAI-compatible HTTP client for Ollama with retries and circuit breaker."""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, cast

import httpx

from inference.config import (
    DEFAULT_CIRCUIT_FAILURE_THRESHOLD,
    DEFAULT_CIRCUIT_RECOVERY_SECONDS,
    advisor_num_predict,
    interactive_num_ctx,
    interactive_temperature,
    llm_api_key,
    llm_base_url,
    max_retries,
    ollama_keep_alive,
    request_timeout_seconds,
)
from inference.telemetry import (
    LlmCallMetrics,
    LlmFeature,
    estimate_messages_tokens,
    estimate_tokens,
    persist_llm_call,
)

logger = logging.getLogger(__name__)


class InferenceUnavailableError(RuntimeError):
    """Raised when inference is unavailable and no fallback applies."""


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    """Simple circuit breaker for repeated upstream failures."""

    failure_threshold: int = DEFAULT_CIRCUIT_FAILURE_THRESHOLD
    recovery_timeout: float = DEFAULT_CIRCUIT_RECOVERY_SECONDS
    consecutive_failures: int = 0
    state: CircuitState = CircuitState.CLOSED
    opened_at: float | None = None

    def allow_request(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if self.opened_at is None:
                return False
            if time.monotonic() - self.opened_at >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                return True
            return False
        # HALF_OPEN: allow a probe request
        return True

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.state = CircuitState.CLOSED
        self.opened_at = None

    def record_failure(self) -> None:
        self.consecutive_failures += 1
        if self.state == CircuitState.HALF_OPEN or self.consecutive_failures >= self.failure_threshold:
            self.state = CircuitState.OPEN
            self.opened_at = time.monotonic()
            logger.warning(
                "Inference circuit opened after %d consecutive failures",
                self.consecutive_failures,
            )


@dataclass
class InferenceClient:
    """OpenAI-compatible client (Ollama /v1 or cloud LLM_BASE_URL)."""

    base_url: str = field(default_factory=llm_base_url)
    api_key: str | None = field(default=None)
    timeout: float = field(default_factory=request_timeout_seconds)
    retries: int = field(default_factory=max_retries)
    circuit_breaker: CircuitBreaker = field(default_factory=CircuitBreaker)
    _client: httpx.Client | None = field(default=None, repr=False, compare=False)
    telemetry_session: Any = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.api_key is None:
            self.api_key = llm_api_key()
        if self._client is None:
            headers: dict[str, str] = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._client = httpx.Client(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout),
                headers=headers,
            )

    def _auth_headers(self) -> dict[str, str]:
        if self.api_key:
            return {"Authorization": f"Bearer {self.api_key}"}
        return {}

    def _interactive_options(self, *, num_predict: int | None = None) -> dict[str, Any]:
        return {
            "num_ctx": interactive_num_ctx(),
            "num_predict": num_predict or advisor_num_predict(),
            "temperature": interactive_temperature(),
            "keep_alive": ollama_keep_alive(),
        }

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> InferenceClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    @property
    def available(self) -> bool:
        return self.circuit_breaker.allow_request()

    def chat_completion(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        response_format: dict[str, Any] | None = None,
        temperature: float | None = None,
        feature: LlmFeature = "extract",
        user_id: uuid.UUID | None = None,
        num_predict: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> str:
        """Return assistant message content from a chat completion."""
        started = time.monotonic()
        prompt_tokens = estimate_messages_tokens(messages)
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": interactive_temperature() if temperature is None else temperature,
            "stream": False,
            **self._interactive_options(num_predict=num_predict),
        }
        if options:
            payload.update(options)
        if response_format is not None:
            payload["response_format"] = response_format

        data = self._post_json("/chat/completions", payload)
        try:
            content = str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise InferenceUnavailableError("Malformed chat completion response") from exc
        completion_tokens = estimate_tokens(content)
        total_ms = int((time.monotonic() - started) * 1000)
        persist_llm_call(
            self.telemetry_session,
            LlmCallMetrics(
                feature=feature,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_ms=total_ms,
                user_id=user_id,
            ),
        )
        return content

    def chat_completion_stream(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        feature: LlmFeature = "advisor",
        user_id: uuid.UUID | None = None,
        num_predict: int | None = None,
    ) -> Iterator[str]:
        """Yield assistant content deltas from a streamed chat completion."""
        if not self.circuit_breaker.allow_request():
            raise InferenceUnavailableError("Inference circuit is open")

        assert self._client is not None
        started = time.monotonic()
        first_token_at: float | None = None
        prompt_tokens = estimate_messages_tokens(messages)
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": interactive_temperature() if temperature is None else temperature,
            "stream": True,
            **self._interactive_options(num_predict=num_predict or max_tokens),
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        collected: list[str] = []
        try:
            with self._client.stream(
                "POST",
                "/chat/completions",
                json=payload,
                headers=self._auth_headers(),
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    data = line[5:].strip() if line.startswith("data:") else line.strip()
                    if not data or data == "[DONE]":
                        if data == "[DONE]":
                            break
                        continue
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    try:
                        delta = chunk["choices"][0].get("delta") or {}
                        content = delta.get("content")
                    except (KeyError, IndexError, TypeError):
                        continue
                    if content:
                        if first_token_at is None:
                            first_token_at = time.monotonic()
                        piece = str(content)
                        collected.append(piece)
                        yield piece
            self.circuit_breaker.record_success()
        except httpx.HTTPError as exc:
            self.circuit_breaker.record_failure()
            logger.warning("Inference stream failed: %s", exc)
            raise InferenceUnavailableError("Inference stream failed") from exc
        finally:
            completion = "".join(collected)
            total_ms = int((time.monotonic() - started) * 1000)
            ttft_ms = (
                int((first_token_at - started) * 1000) if first_token_at is not None else None
            )
            persist_llm_call(
                self.telemetry_session,
                LlmCallMetrics(
                    feature=feature,
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=estimate_tokens(completion),
                    time_to_first_token_ms=ttft_ms,
                    total_ms=total_ms,
                    user_id=user_id,
                ),
            )

    def embeddings(self, *, model: str, input_text: str | list[str]) -> list[list[float]]:
        """Return embedding vectors for one or more inputs."""
        payload = {"model": model, "input": input_text}
        data = self._post_json("/embeddings", payload)
        try:
            items = sorted(data["data"], key=lambda item: item["index"])
            return [list(item["embedding"]) for item in items]
        except (KeyError, TypeError) as exc:
            raise InferenceUnavailableError("Malformed embeddings response") from exc

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.circuit_breaker.allow_request():
            raise InferenceUnavailableError("Inference circuit is open")

        assert self._client is not None
        last_error: Exception | None = None
        attempts = self.retries + 1

        for attempt in range(attempts):
            try:
                response = self._client.post(
                    path,
                    json=payload,
                    headers=self._auth_headers(),
                )
                response.raise_for_status()
                data = response.json()
                self.circuit_breaker.record_success()
                return cast(dict[str, Any], data)
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                self.circuit_breaker.record_failure()
                logger.warning(
                    "Inference request failed (attempt %d/%d): %s",
                    attempt + 1,
                    attempts,
                    exc,
                )
                if attempt + 1 >= attempts:
                    break

        message = f"Inference request failed after {attempts} attempts"
        if last_error is not None:
            raise InferenceUnavailableError(message) from last_error
        raise InferenceUnavailableError(message)


_chat_client: InferenceClient | None = None
_embedding_client: InferenceClient | None = None


def get_client() -> InferenceClient:
    """Chat/completion client (normalization, advisor, resume builder)."""
    return get_chat_client()


def get_chat_client() -> InferenceClient:
    global _chat_client
    if _chat_client is None:
        _chat_client = InferenceClient()
    return _chat_client


def get_embedding_client() -> InferenceClient:
    """Embedding client with an isolated circuit breaker from chat workloads."""
    global _embedding_client
    if _embedding_client is None:
        _embedding_client = InferenceClient()
    return _embedding_client
