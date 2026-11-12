"""Apply-assist LLM drafts for form answers."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from typing import Any

from inference.client import InferenceClient, InferenceUnavailableError, get_client
from inference.config import apply_assist_reply_max_chars, apply_assist_reply_max_tokens
from inference.extraction import ExtractionError, _chat_json
from inference.prompts import load_prompt

logger = logging.getLogger(__name__)

_REPLY_MAX_TOKENS = apply_assist_reply_max_tokens()
_STREAM_RULES = (
    "\n\nReply in plain chat text (not JSON). Light markdown OK. "
    "Draft concise application answers from the profile/identity only. "
    "Never invent employers, dates, credentials, or salary history. "
    "If evidence is missing, say what the user should fill in. "
    "If the selection is a form field, produce an answer ready to paste."
)


def apply_assist_stream(
    *,
    profile: dict[str, Any],
    identity: dict[str, Any],
    page_url: str,
    page_title: str,
    selection_text: str,
    selection_tag: str,
    is_editable: bool,
    question: str,
    job: dict[str, Any] | None = None,
    client: InferenceClient | None = None,
) -> Iterator[str]:
    llm = client or get_client()
    loaded = load_prompt("apply_assist")
    payload = {
        "profile": profile,
        "identity": identity,
        "page": {"url": page_url, "title": page_title},
        "selection": {
            "text": selection_text[:4000],
            "tag": selection_tag,
            "is_editable": is_editable,
        },
        "job": job,
        "question": question.strip(),
    }
    system = loaded.system_message + _STREAM_RULES
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
    try:
        produced = False
        for chunk in llm.chat_completion_stream(
            model=loaded.model,
            messages=messages,
            max_tokens=_REPLY_MAX_TOKENS,
        ):
            if not chunk:
                continue
            produced = True
            yield chunk
        if not produced:
            raise InferenceUnavailableError("Empty stream")
    except InferenceUnavailableError as exc:
        logger.warning("apply assist stream unavailable: %s", exc)
        yield (
            "I couldn’t reach the drafting model. Use your profile manually: "
            "preferred name, email, phone, and role highlights from Experience."
        )


def apply_assist_reply(
    *,
    profile: dict[str, Any],
    identity: dict[str, Any],
    page_url: str,
    page_title: str,
    selection_text: str,
    selection_tag: str,
    is_editable: bool,
    question: str,
    job: dict[str, Any] | None = None,
    client: InferenceClient | None = None,
) -> str:
    llm = client or get_client()
    loaded = load_prompt("apply_assist")
    payload = {
        "profile": profile,
        "identity": identity,
        "page": {"url": page_url, "title": page_title},
        "selection": {
            "text": selection_text[:4000],
            "tag": selection_tag,
            "is_editable": is_editable,
        },
        "job": job,
        "question": question.strip(),
    }
    try:
        data = _chat_json(llm, loaded, json.dumps(payload, ensure_ascii=False), max_attempts=2)
        reply = str(data.get("reply") or "").strip()
        if len(reply) < 8:
            raise ExtractionError("Apply assist reply too short")
        return reply[: apply_assist_reply_max_chars()]
    except (InferenceUnavailableError, ExtractionError, ValueError) as exc:
        logger.warning("apply assist unavailable: %s", exc)
        return (
            "Model unavailable. Fill from your saved profile: name, email, phone, "
            "and highlights under Experience."
        )
