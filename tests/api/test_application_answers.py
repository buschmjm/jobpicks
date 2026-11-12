"""Saved application answers vault API tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

from api.main import app
from api.repositories.saved_application_answer_repo import SavedApplicationAnswerRepository
from api.repositories.todo_repo import TodoRepository
from api.services.application_packet_service import application_packet_service
from api.services.auth_service import auth_service
from core.models import Job, JobStatus, RemoteMode
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def _user_id(db_session: Session) -> str:
    _, user_id = auth_service.verify_and_create_session(db_session, "vault@example.com")
    db_session.commit()
    return str(user_id)


def test_vault_crud_service_layer(db_session: Session) -> None:
    from api.schemas import SavedApplicationAnswerUpsertRequest
    from api.services.saved_application_answer_service import saved_application_answer_service

    user_id = __import__("uuid").UUID(_user_id(db_session))
    created = saved_application_answer_service.upsert(
        db_session,
        user_id,
        "work_authorization",
        SavedApplicationAnswerUpsertRequest(
            question_text="Authorized to work in the US?",
            answer="Yes, US citizen.",
        ),
    )
    assert created.question_key == "work_authorization"

    listed = saved_application_answer_service.list_answers(db_session, user_id)
    assert len(listed.items) == 1

    updated = saved_application_answer_service.upsert(
        db_session,
        user_id,
        "work_authorization",
        SavedApplicationAnswerUpsertRequest(
            question_text="Work authorization",
            answer="Yes.",
        ),
    )
    assert updated.answer == "Yes."

    assert saved_application_answer_service.delete(db_session, user_id, "work_authorization")


def test_packet_generate_merges_vault(db_session: Session) -> None:
    user_id = __import__("uuid").UUID(_user_id(db_session))
    job = Job(
        company_name="Acme",
        title="Engineer",
        normalized_title="engineer",
        canonical_hash=f"hash-{uuid4()}",
        status=JobStatus.OPEN,
        remote_mode=RemoteMode.REMOTE,
        description="Build",
        source_url="https://example.com/jobs/1",
        primary_source="test",
    )
    db_session.add(job)
    db_session.flush()
    todo = TodoRepository(db_session).create(user_id, job.id)
    db_session.commit()

    SavedApplicationAnswerRepository(db_session).upsert(
        user_id,
        question_key="work_authorization",
        question_text="Work auth?",
        answer="Yes, authorized.",
    )
    db_session.commit()

    with (
        patch(
            "api.services.application_packet_service.propose_application_packet",
            return_value={
                "fit_verdict": "apply",
                "fit_rationale": ["ok"],
                "cover_letter": "Dear team,\n\nLetter body for testing.\n\nThanks",
                "answers": [
                    {
                        "key": "work_authorization",
                        "question_text": "Work auth?",
                        "suggested_answer": "Maybe",
                        "source": "llm",
                        "status": "pending",
                    }
                ],
            },
        ),
        patch(
            "api.services.application_packet_service.resume_service.tailor",
            return_value=MagicMock(draft=MagicMock(id=uuid4()), source="template"),
        ),
    ):
        packet = application_packet_service.generate(db_session, user_id, todo.id)

    work_auth = next(a for a in packet.answers if a.key == "work_authorization")
    assert work_auth.source.value == "vault"
    assert work_auth.status.value == "confirmed"
    assert work_auth.suggested_answer == "Yes, authorized."


def test_patch_auto_saves_common_keys(db_session: Session) -> None:
    user_id = __import__("uuid").UUID(_user_id(db_session))
    job = Job(
        company_name="Acme",
        title="Engineer",
        normalized_title="engineer",
        canonical_hash=f"hash-{uuid4()}",
        status=JobStatus.OPEN,
        remote_mode=RemoteMode.REMOTE,
        description="Build",
        source_url="https://example.com/jobs/2",
        primary_source="test",
    )
    db_session.add(job)
    db_session.flush()
    todo = TodoRepository(db_session).create(user_id, job.id)
    db_session.commit()

    with (
        patch(
            "api.services.application_packet_service.propose_application_packet",
            return_value={
                "fit_verdict": "apply",
                "fit_rationale": ["ok"],
                "cover_letter": "Dear team,\n\nLetter.\n\nThanks",
                "answers": [
                    {
                        "key": "sponsorship",
                        "question_text": "Sponsorship?",
                        "suggested_answer": "No",
                        "source": "llm",
                        "status": "pending",
                    }
                ],
            },
        ),
        patch(
            "api.services.application_packet_service.resume_service.tailor",
            return_value=MagicMock(draft=MagicMock(id=uuid4()), source="template"),
        ),
    ):
        application_packet_service.generate(db_session, user_id, todo.id)

    from api.schemas import ApplicationPacketPatchRequest, PacketAnswerPatchItem, PacketAnswerStatus

    application_packet_service.patch(
        db_session,
        user_id,
        todo.id,
        ApplicationPacketPatchRequest(
            answers=[
                PacketAnswerPatchItem(
                    key="sponsorship",
                    status=PacketAnswerStatus.confirmed,
                    final_answer="No sponsorship required.",
                )
            ]
        ),
    )

    saved = SavedApplicationAnswerRepository(db_session).get_by_key(user_id, "sponsorship")
    assert saved is not None
    assert saved.answer == "No sponsorship required."


def test_vault_requires_auth() -> None:
    client = TestClient(app)
    assert client.get("/api/application-answers").status_code == 401
    assert (
        client.put(
            "/api/application-answers/work_authorization",
            json={"question_text": "Q", "answer": "A"},
        ).status_code
        == 401
    )
