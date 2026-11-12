"""JSON-schema-validated LLM extraction for resumes and jobs."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from jsonschema import Draft202012Validator, ValidationError

from inference.client import InferenceClient, InferenceUnavailableError, get_chat_client
from inference.prompts import LoadedPrompt, load_prompt

logger = logging.getLogger(__name__)

JSON_BLOCK_PATTERN = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


class ExtractionError(ValueError):
    """Raised when extraction fails after retries."""


def _strip_json_fence(content: str) -> str:
    content = content.strip()
    match = JSON_BLOCK_PATTERN.search(content)
    if match:
        return match.group(1).strip()
    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end != -1 and end > start:
        return content[start : end + 1]
    return content


def _parse_json(content: str) -> dict[str, Any]:
    cleaned = _strip_json_fence(content)
    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise ValueError("Expected a JSON object")
    return parsed


def _validate_against_schema(data: dict[str, Any], schema: dict[str, Any]) -> None:
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda err: err.path)
    if errors:
        messages = "; ".join(error.message for error in errors[:5])
        raise ValidationError(messages)


def _chat_json(
    client: InferenceClient,
    prompt: LoadedPrompt,
    user_content: str,
    *,
    max_attempts: int = 2,
) -> dict[str, Any]:
    """Call the LLM and validate JSON output, retrying on invalid responses."""
    messages = [
        {"role": "system", "content": prompt.system_message},
        {"role": "user", "content": user_content},
    ]
    response_format = {"type": "json_object"}
    last_error: Exception | None = None

    raw = ""
    for attempt in range(max_attempts):
        try:
            raw = client.chat_completion(
                model=prompt.model,
                messages=messages,
                response_format=response_format,
                temperature=0.0,
            )
            data = _parse_json(raw)
            _validate_against_schema(data, prompt.schema)
            return data
        except (InferenceUnavailableError, json.JSONDecodeError, ValidationError, ValueError) as exc:
            last_error = exc
            logger.warning(
                "Extraction attempt %d/%d failed for prompt %s v%s: %s",
                attempt + 1,
                max_attempts,
                prompt.name,
                prompt.version,
                exc,
            )
            if attempt + 1 < max_attempts:
                messages.append({"role": "assistant", "content": raw})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Your previous response was invalid JSON or did not match the "
                            f"required schema. Error: {exc}. Return ONLY valid JSON matching "
                            "the schema."
                        ),
                    }
                )

    message = f"Extraction failed for prompt {prompt.name} after {max_attempts} attempts"
    if last_error is not None:
        raise ExtractionError(message) from last_error
    raise ExtractionError(message)


def extract_resume_profile(
    resume_text: str,
    *,
    client: InferenceClient | None = None,
    prompt: LoadedPrompt | None = None,
    max_attempts: int = 2,
) -> dict[str, Any]:
    """Parse a resume into a structured profile with per-fact status."""
    llm = client or get_chat_client()
    loaded = prompt or load_prompt("resume_parse")
    return _chat_json(llm, loaded, resume_text, max_attempts=max_attempts)


def extract_job_fields(
    job_text: str,
    *,
    client: InferenceClient | None = None,
    prompt: LoadedPrompt | None = None,
    max_attempts: int = 2,
) -> dict[str, Any]:
    """Normalize unstructured job posting text (Adzuna/Remotive/ATS)."""
    llm = client or get_chat_client()
    loaded = prompt or load_prompt("job_normalize")
    return _chat_json(llm, loaded, job_text, max_attempts=max_attempts)
