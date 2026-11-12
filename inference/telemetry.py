"""Persist per-LLM-call telemetry for COGS tracking and admin dashboards."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Literal

from core.models import LlmCallLog
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

LlmFeature = Literal["advisor", "builder", "extract", "normalize", "packet"]


@dataclass(frozen=True)
class LlmCallMetrics:
    feature: LlmFeature
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_ms: int
    time_to_first_token_ms: int | None = None
    user_id: uuid.UUID | None = None


def estimate_tokens(text: str) -> int:
    """Rough token estimate without an external tokenizer (≈4 chars/token)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def estimate_messages_tokens(messages: list[dict[str, str]]) -> int:
    return sum(estimate_tokens(str(m.get("content", ""))) for m in messages)


def persist_llm_call(session: Session | None, metrics: LlmCallMetrics) -> None:
    """Write one telemetry row; no-op when session is None (tests/offline)."""
    if session is None:
        logger.debug(
            "llm_call feature=%s model=%s prompt_tok=%d completion_tok=%d total_ms=%d ttft_ms=%s",
            metrics.feature,
            metrics.model,
            metrics.prompt_tokens,
            metrics.completion_tokens,
            metrics.total_ms,
            metrics.time_to_first_token_ms,
        )
        return
    row = LlmCallLog(
        id=uuid.uuid4(),
        feature=metrics.feature,
        model=metrics.model,
        prompt_tokens=metrics.prompt_tokens,
        completion_tokens=metrics.completion_tokens,
        time_to_first_token_ms=metrics.time_to_first_token_ms,
        total_ms=metrics.total_ms,
        user_id=metrics.user_id,
    )
    session.add(row)
    try:
        session.flush()
    except Exception:
        logger.warning("failed to persist llm_call_log", exc_info=True)
