"""Tests for resume builder chat API and service."""

from __future__ import annotations

import json
from contextlib import contextmanager
from unittest.mock import patch

from api.main import app
from api.repositories.user_repo import UserRepository
from api.schemas import ResumeBuilderMessageCreate
from api.services.resume_builder_chat_service import (
    clear_thread,
    get_thread,
    iter_builder_sse,
    prepare_stream,
    send_message,
)
from api.services.resume_proposal_service import list_proposals
from fastapi.testclient import TestClient
from inference.resume_builder import BuilderReply
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


def test_get_thread_empty_creates_default_variant(db_session: Session) -> None:
    user = UserRepository(db_session).get_or_create_by_email("builder@example.com")
    db_session.commit()
    thread = get_thread(db_session, user.id)
    assert thread.messages == []


def test_send_message_sync_persists(db_session: Session) -> None:
    user = UserRepository(db_session).get_or_create_by_email("builder-sync@example.com")
    db_session.commit()

    mock_reply = BuilderReply(
        reply="Tell me about your most recent role: title, employer, and dates.",
        source="template",
    )
    with patch(
        "api.services.resume_builder_chat_service.resume_builder_sync",
        return_value=mock_reply,
    ), patch(
        "api.services.resume_builder_chat_service.build_profile_snapshot",
        return_value={"schema": "jobdeck.profile.v2", "roles": []},
    ):
        thread = send_message(
            db_session,
            user.id,
            ResumeBuilderMessageCreate(content="Help me build my resume"),
        )

    assert len(thread.messages) == 2
    assert thread.messages[0].role == "user"
    assert thread.messages[1].role == "assistant"
    assert thread.messages[1].source == "template"

    variant_id = thread.messages[0].variant_id
    cleared = clear_thread(db_session, user.id, variant_id=variant_id)
    assert cleared.messages == []
    assert get_thread(db_session, user.id, variant_id=variant_id).messages == []


def test_send_message_sync_creates_proposal(db_session: Session) -> None:
    user = UserRepository(db_session).get_or_create_by_email("builder-proposal@example.com")
    db_session.commit()

    proposal = {
        "summary": "Add Platform Engineer role",
        "roles": [
            {
                "title": "Platform Engineer",
                "company_name": "Acme",
                "start_date": "2022-01",
                "end_date": "present",
                "is_current": True,
                "highlights": ["Built CI/CD pipelines"],
            }
        ],
    }
    mock_reply = BuilderReply(
        reply="Here is a draft update for your platform role.",
        source="llm",
        proposal=proposal,
    )
    with patch(
        "api.services.resume_builder_chat_service.resume_builder_sync",
        return_value=mock_reply,
    ), patch(
        "api.services.resume_builder_chat_service.build_profile_snapshot",
        return_value={"schema": "jobdeck.profile.v2", "roles": []},
    ):
        thread = send_message(
            db_session,
            user.id,
            ResumeBuilderMessageCreate(content="I was a platform engineer at Acme since 2022"),
        )

    variant_id = thread.messages[0].variant_id
    assert variant_id is not None
    proposals = list_proposals(db_session, user.id, variant_id=variant_id)
    assert len(proposals.proposals) == 1
    assert proposals.proposals[0].status.value == "pending"
    assert proposals.proposals[0].operations


def test_prepare_stream_creates_pending_assistant(db_session: Session) -> None:
    user = UserRepository(db_session).get_or_create_by_email("builder-pending@example.com")
    db_session.commit()
    prep = prepare_stream(
        db_session,
        user.id,
        ResumeBuilderMessageCreate(content="Let's update my resume bullets"),
    )
    thread = get_thread(db_session, user.id, variant_id=prep.variant_id)
    assert len(thread.messages) == 2
    assert thread.messages[0].role == "user"
    assert thread.messages[1].role == "assistant"
    assert thread.messages[1].status == "pending"
    assert thread.messages[1].content == ""
    assert prep.assistant_message_id == thread.messages[1].id


def test_iter_builder_sse_stream_completes(db_session: Session) -> None:
    user = UserRepository(db_session).get_or_create_by_email("builder-stream@example.com")
    db_session.commit()
    prep = prepare_stream(
        db_session,
        user.id,
        ResumeBuilderMessageCreate(content="What bullets should I add?"),
    )

    reply_text = (
        "Share metrics for your latest role.\n"
        "---PROPOSAL---\n"
        '{"summary":"Add bullets","roles":[{"title":"Engineer","company_name":"Acme","highlights":["Shipped v1"]}]}'
    )

    def fake_stream(**kwargs):
        step = 64
        for offset in range(0, len(reply_text), step):
            yield reply_text[offset : offset + step], "llm"

    @contextmanager
    def fake_factory():
        yield db_session

    with (
        patch("api.services.resume_builder_chat_service.threading.Thread", _SyncThread),
        patch(
            "api.services.resume_builder_chat_service.resume_builder_stream",
            side_effect=fake_stream,
        ),
        patch(
            "api.services.resume_builder_chat_service.build_profile_snapshot",
            return_value={"schema": "jobdeck.profile.v2"},
        ),
        patch("api.services.resume_builder_chat_service.get_session_factory", return_value=fake_factory),
    ):
        events = _parse_sse("".join(iter_builder_sse(prep)))

    types = [e["type"] for e in events]
    assert "user" in types
    assert "token" in types
    assert "done" in types
    assert "error" not in types

    thread = get_thread(db_session, user.id, variant_id=prep.variant_id)
    assert thread.messages[-1].status == "complete"
    assert "Share metrics" in thread.messages[-1].content


def test_resume_chat_messages_requires_auth() -> None:
    client = TestClient(app)
    assert client.get("/api/resume/chat/messages").status_code == 401
    assert client.delete("/api/resume/chat/messages").status_code == 401
