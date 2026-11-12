"""Long-response streaming tests for the career advisor chat."""

from __future__ import annotations

import json
from contextlib import contextmanager
from unittest.mock import patch

from api.repositories.user_repo import UserRepository
from api.schemas import CareerMessageCreate
from api.services.career_advisor_service import (
    _finalize_advisor_reply,
    _stream_token_chunk,
    get_thread,
    iter_advisor_sse,
    prepare_stream,
)
from sqlalchemy.orm import Session


class _SyncThread:
    def __init__(self, target, args=(), kwargs=None, daemon=None, name=None):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self) -> None:
        self._target(*self._args, **self._kwargs)

    def is_alive(self) -> bool:
        return False

    def join(self, timeout: float | None = None) -> None:
        return None


def _parse_sse(body: str) -> list[dict]:
    events = []
    for block in body.split("\n\n"):
        line = next((ln for ln in block.split("\n") if ln.startswith("data:")), None)
        if not line:
            continue
        events.append(json.loads(line[5:].strip()))
    return events


def test_stream_token_chunk_emits_full_long_reply() -> None:
    long_chunk = "A" * 5000
    emitted = 0
    parts: list[str] = []
    for _ in range(10):
        text, emitted = _stream_token_chunk(long_chunk, emitted, max_chars=8000)
        if text:
            parts.append(text)
    assert len("".join(parts)) == 8000


def test_finalize_advisor_reply_keeps_long_markdown() -> None:
    body = (
        "**Lean apply.**\n\n"
        + "- Strong platform background\n"
        + "- Missing one must-have\n\n"
        + ("Detail sentence. " * 400)
    ).strip()
    reply = _finalize_advisor_reply([body], max_chars=8000)
    assert reply.startswith("**Lean apply.**")
    assert len(reply) >= 6000
    assert len(reply) <= 8000


def test_finalize_advisor_reply_strips_thinking_blocks() -> None:
    open_tag = "<" + "think" + ">"
    close_tag = "</" + "think" + ">"
    raw = (
        f"{open_tag}\ninternal reasoning only\n{close_tag}\n\n"
        "**Apply.** Your SRE background matches the posting requirements."
    )
    reply = _finalize_advisor_reply([raw], max_chars=8000)
    assert "internal reasoning" not in reply
    assert reply.startswith("**Apply.**")


def test_iter_advisor_sse_long_response_completes_without_error(db_session: Session) -> None:
    user = UserRepository(db_session).get_or_create_by_email("advisor-long@example.com")
    db_session.commit()
    prep = prepare_stream(
        db_session,
        user.id,
        CareerMessageCreate(content="Give me a detailed fit assessment with many bullets."),
    )

    long_reply = (
        "**Lean apply.**\n\n"
        "Matches:\n"
        + "\n".join(f"- Evidence point {i}" for i in range(1, 41))
        + "\n\nGaps:\n"
        + "\n".join(f"- Gap {i}" for i in range(1, 21))
        + "\n\n"
        + ("Closing guidance sentence. " * 120)
    )

    def fake_stream(**kwargs):
        step = 64
        for offset in range(0, len(long_reply), step):
            yield long_reply[offset : offset + step], "llm"

    @contextmanager
    def fake_factory():
        yield db_session

    with (
        patch("api.services.career_advisor_service.threading.Thread", _SyncThread),
        patch("api.services.career_advisor_service.advisor_research_enabled", return_value=False),
        patch(
            "api.services.career_advisor_service.career_advisor_stream",
            side_effect=fake_stream,
        ),
        patch("api.services.career_advisor_service.build_profile_snapshot", return_value={}),
        patch("api.services.career_advisor_service.get_session_factory", return_value=fake_factory),
    ):
        events = _parse_sse("".join(iter_advisor_sse(prep)))

    assert not any(event.get("type") == "error" for event in events)
    assert events[-1]["type"] == "done"
    done = events[-1]
    assert done["message"]["role"] == "assistant"
    assert done["message"]["status"] == "complete"
    assert len(done["message"]["content"]) >= 3000
    token_text = "".join(event["text"] for event in events if event["type"] == "token")
    assert len(token_text) >= 3000
    assert token_text.startswith("**Lean apply.**")

    thread = get_thread(db_session, user.id)
    assert len(thread.messages) == 2
    assert thread.messages[1].status == "complete"
    assert len(thread.messages[1].content) >= 3000
