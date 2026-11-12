"""Tests for career advisor chat API."""

from __future__ import annotations

from unittest.mock import patch

from api.main import app
from api.repositories.profile_repo import ProfileRepository
from api.repositories.user_repo import UserRepository
from api.schemas import CareerMessageCreate, FactStatus, ProfileFact
from api.services.career_advisor_service import (
    clear_thread,
    get_thread,
    prepare_stream,
    request_cancel,
    send_message,
)
from fastapi.testclient import TestClient
from inference.career_advisor import AdvisorReply
from sqlalchemy.orm import Session


def test_get_thread_empty(db_session: Session) -> None:
    user = UserRepository(db_session).get_or_create_by_email("advisor@example.com")
    db_session.commit()
    thread = get_thread(db_session, user.id)
    assert thread.messages == []


def test_send_message_persists(db_session: Session) -> None:
    user = UserRepository(db_session).get_or_create_by_email("advisor2@example.com")
    db_session.commit()
    ProfileRepository(db_session).save_confirmed_facts(
        user.id,
        [ProfileFact(key="full_name", value="Alex", status=FactStatus.confirmed)],
    )
    db_session.commit()

    mock_reply = AdvisorReply(
        reply="Your SRE background maps well to platform engineering roles in the US market.",
        source="template",
    )
    with patch("api.services.career_advisor_service.career_advisor_reply", return_value=mock_reply), patch(
        "api.services.career_advisor_service._run_research",
        return_value=None,
    ):
        thread = send_message(db_session, user.id, CareerMessageCreate(content="What roles fit me?"))

    assert len(thread.messages) == 2
    assert thread.messages[0].role == "user"
    assert thread.messages[1].role == "assistant"
    assert thread.messages[1].source == "template"

    cleared = clear_thread(db_session, user.id)
    assert cleared.messages == []
    assert get_thread(db_session, user.id).messages == []


def test_prepare_stream_creates_pending_assistant(db_session: Session) -> None:
    user = UserRepository(db_session).get_or_create_by_email("advisor-pending@example.com")
    db_session.commit()
    prep = prepare_stream(
        db_session,
        user.id,
        CareerMessageCreate(content="What roles fit me?"),
    )
    thread = get_thread(db_session, user.id)
    assert len(thread.messages) == 2
    assert thread.messages[0].role == "user"
    assert thread.messages[1].role == "assistant"
    assert thread.messages[1].status == "pending"
    assert thread.messages[1].content == ""
    assert prep.assistant_message_id == thread.messages[1].id


def test_career_messages_requires_auth() -> None:
    client = TestClient(app)
    assert client.get("/api/career/messages").status_code == 401
    assert client.delete("/api/career/messages").status_code == 401


def test_cancel_pending_assistant_message(db_session: Session) -> None:
    user = UserRepository(db_session).get_or_create_by_email("advisor-cancel@example.com")
    db_session.commit()
    prep = prepare_stream(
        db_session,
        user.id,
        CareerMessageCreate(content="Long question"),
    )
    cancelled = request_cancel(db_session, user.id, prep.assistant_message_id)
    assert cancelled.status == "cancelled"
    assert cancelled.content == "Response stopped."
