"""Structured chat prompt assembly (Workstream A3)."""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from typing import Any

from inference.prompts import FRONT_MATTER_PATTERN, PROMPTS_DIR, LoadedPrompt
from inference.telemetry import estimate_tokens

logger = logging.getLogger(__name__)

MAX_PROMPT_TOKENS = 3000
MAX_CONTEXT_TOKENS = 600
MAX_HISTORY_MESSAGES = 6

_PII_PATTERNS = (
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),  # SSN-like
    re.compile(r"\b\d{9}\b"),
    re.compile(r"https?://\S+\.(?:jpg|jpeg|png|gif|webp)\b", re.I),
)
_STREET_PATTERN = re.compile(
    r"\b\d{1,5}\s+\w+\s+(?:street|st|avenue|ave|road|rd|boulevard|blvd|lane|ln|drive|dr)\b",
    re.I,
)


@lru_cache(maxsize=32)
def system_prompt_bytes(prompt_name: str) -> bytes:
    """Return byte-identical system prompt body for a versioned prompts/*.md file."""
    path = PROMPTS_DIR / f"{prompt_name}.md"
    raw = path.read_bytes()
    match = FRONT_MATTER_PATTERN.match(raw.decode("utf-8"))
    if not match:
        raise ValueError(f"Prompt {path} is missing YAML front-matter")
    return match.group(2).strip().encode("utf-8")


def system_prompt_text(prompt_name: str) -> str:
    return system_prompt_bytes(prompt_name).decode("utf-8")


def _strip_pii(value: Any) -> Any:
    if isinstance(value, str):
        cleaned = value
        for pattern in _PII_PATTERNS:
            cleaned = pattern.sub("[redacted]", cleaned)
        cleaned = _STREET_PATTERN.sub("[address]", cleaned)
        return cleaned
    if isinstance(value, dict):
        blocked = {"name", "full_name", "first_name", "last_name", "email", "phone", "dob", "date_of_birth"}
        return {
            k: _strip_pii(v)
            for k, v in value.items()
            if k.lower() not in blocked
        }
    if isinstance(value, list):
        return [_strip_pii(item) for item in value]
    return value


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    if estimate_tokens(text) <= max_tokens:
        return text
    budget_chars = max_tokens * 4
    if len(text) <= budget_chars:
        return text
    truncated = text[: budget_chars - 1].rstrip() + "…"
    logger.info("prompt context truncated from ~%d to ~%d tokens", estimate_tokens(text), max_tokens)
    return truncated


_RAW_TEXT_KEYS = frozenset(
    {"description", "job_description", "resume_text", "raw_resume", "raw_job"}
)


def _omit_raw_text_fields(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if key in _RAW_TEXT_KEYS:
                cleaned[key] = "[omitted — use structured fields only]"
            else:
                cleaned[key] = _omit_raw_text_fields(item)
        return cleaned
    if isinstance(value, list):
        return [_omit_raw_text_fields(item) for item in value]
    return value


def structured_context_block(context: dict[str, Any]) -> str:
    """Serialize structured context — never raw resume/job posting bodies."""
    sanitized = _strip_pii(_omit_raw_text_fields(context))
    text = json.dumps(sanitized, separators=(",", ":"), ensure_ascii=False)
    return _truncate_to_tokens(text, MAX_CONTEXT_TOKENS)


def build_chat_messages(
    *,
    prompt_name: str,
    structured_context: dict[str, Any],
    history: list[dict[str, str]],
    user_message: str,
    extra_system_suffix: str = "",
) -> list[dict[str, str]]:
    """
    Assemble messages: static system → structured context → history → user.
    Total budget ≤ MAX_PROMPT_TOKENS (enforced with truncation + log).
    """
    system_text = system_prompt_text(prompt_name)
    if extra_system_suffix:
        system_text = system_text + extra_system_suffix

    context_json = structured_context_block(structured_context)
    system_with_context = f"{system_text}\n\n<context>\n{context_json}\n</context>"

    trimmed_history = []
    for turn in history[-MAX_HISTORY_MESSAGES:]:
        role = turn.get("role")
        content = (turn.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            trimmed_history.append({"role": role, "content": content})

    messages: list[dict[str, str]] = [{"role": "system", "content": system_with_context}]
    messages.extend(trimmed_history)
    messages.append({"role": "user", "content": user_message.strip()})

    total = sum(estimate_tokens(m["content"]) for m in messages)
    if total > MAX_PROMPT_TOKENS:
        # Drop oldest history turns until within budget.
        while len(messages) > 2 and total > MAX_PROMPT_TOKENS:
            if len(messages) > 2 and messages[1]["role"] in ("user", "assistant"):
                removed = messages.pop(1)
                total -= estimate_tokens(removed["content"])
            else:
                break
        if total > MAX_PROMPT_TOKENS:
            messages[0]["content"] = _truncate_to_tokens(
                messages[0]["content"],
                MAX_PROMPT_TOKENS - estimate_tokens(user_message) - 50,
            )
            logger.info("prompt builder enforced MAX_PROMPT_TOKENS budget")

    return messages


def loaded_prompt_system_bytes(loaded: LoadedPrompt) -> bytes:
    return loaded.body.strip().encode("utf-8")
