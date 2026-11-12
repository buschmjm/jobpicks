"""Application packet API tests."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

from api.main import app
from api.repositories.todo_repo import TodoRepository
from api.schemas import (
    ApplicationPacketPatchRequest,
    PacketAnswerPatchItem,
    PacketAnswerStatus,
    ResumeDraftResponse,
)
from api.services.application_packet_service import application_packet_service
from api.services.auth_service import auth_service
from core.models import Job, JobStatus, RemoteMode
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def _seed_todo(db_session: Session) -> tuple[UUID, UUID, str]:
    token, user_id = auth_service.verify_and_create_session(db_session, "packet@example.com")
    job = Job(
        company_name="Globex",
        title="Platform Engineer",
        normalized_title="platform engineer",
        canonical_hash=f"hash-{uuid4()}",
        status=JobStatus.OPEN,
        remote_mode=RemoteMode.REMOTE,
        description="Build platforms with Kubernetes.",
        source_url="https://www.linkedin.com/jobs/view/123",
        apply_url="https://boards.greenhouse.io/globex/jobs/123",
        ats_type="greenhouse",
        ats_metadata={"board_token": "globex", "posting_id": "123"},
        primary_source="test",
    )
    db_session.add(job)
    db_session.flush()
    todo = TodoRepository(db_session).create(user_id, job.id)
    db_session.commit()
    return user_id, todo.id, token


def _mock_tailor() -> MagicMock:
    return MagicMock(
        draft=ResumeDraftResponse(
            id=uuid4(),
            job_id=None,
            status="draft",
            layout="ats",
            document={},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
        source="template",
    )


def _mock_proposal() -> dict:
    return {
        "fit_verdict": "apply",
        "fit_rationale": ["Strong Kubernetes match"],
        "source": "llm",
    }


def _mock_cover_letter() -> str:
    return (
        "Dear Hiring Manager,\n\n"
        "I am applying for the Platform Engineer role at Globex. "
        "I have led Kubernetes platform work across distributed teams and delivered reliable infrastructure.\n\n"
        "At my current employer, I automated cluster provisioning and reduced deployment lead time by 35%. "
        "I also partnered with application teams to standardize observability and incident response.\n\n"
        "Globex's focus on scalable platform engineering aligns with the work I have done in production. "
        "I would welcome the opportunity to discuss how I can contribute.\n\n"
        "Sincerely,\nJordan Lee"
    )


def test_packet_requires_auth() -> None:
    client = TestClient(app)
    item_id = uuid4()
    assert client.get(f"/api/todo/{item_id}/packet").status_code == 401
    assert client.post(f"/api/todo/{item_id}/packet").status_code == 401
    assert client.patch(f"/api/todo/{item_id}/packet", json={}).status_code == 401
    assert client.post(f"/api/todo/{item_id}/packet/open").status_code == 401


def test_generate_packet_for_todo(db_session: Session) -> None:
    user_id, todo_id, _ = _seed_todo(db_session)
    with (
        patch(
            "api.services.application_packet_service.propose_application_packet",
            return_value=_mock_proposal(),
        ),
        patch(
            "api.services.application_packet_service.resume_service.tailor",
            return_value=_mock_tailor(),
        ),
        patch(
            "api.services.application_packet_service.draft_cover_letter",
            return_value=_mock_cover_letter(),
        ),
    ):
        packet = application_packet_service.execute_generate(db_session, user_id, todo_id)

    assert packet.status == "ready"
    assert packet.todo_item_id == todo_id
    assert packet.fit_verdict == "apply"
    assert packet.resume_draft_id is not None
    assert len(packet.answers) == 0
    assert "Platform Engineer" in (packet.cover_letter or "")
    assert packet.apply_url == "https://boards.greenhouse.io/globex/jobs/123"
    assert packet.ats_type == "greenhouse"


def test_request_generate_returns_immediately_and_enqueues(db_session: Session) -> None:
    user_id, todo_id, _ = _seed_todo(db_session)
    with patch("api.services.application_packet_service.enqueue_job") as enqueue_mock:
        packet = application_packet_service.request_generate(db_session, user_id, todo_id)

    assert packet.status == "generating"
    assert packet.todo_item_id == todo_id
    enqueue_mock.assert_called_once()
    assert enqueue_mock.call_args.args[1] == "packet_prefetch"


def test_get_packet(db_session: Session) -> None:
    user_id, todo_id, _ = _seed_todo(db_session)
    with (
        patch(
            "api.services.application_packet_service.propose_application_packet",
            return_value=_mock_proposal(),
        ),
        patch(
            "api.services.application_packet_service.resume_service.tailor",
            return_value=_mock_tailor(),
        ),
        patch(
            "api.services.application_packet_service.draft_cover_letter",
            return_value=_mock_cover_letter(),
        ),
    ):
        generated = application_packet_service.generate(db_session, user_id, todo_id)

    fetched = application_packet_service.get(db_session, user_id, todo_id)
    assert fetched is not None
    assert fetched.id == generated.id
    assert fetched.cover_letter == generated.cover_letter


def test_patch_confirms_answers(db_session: Session) -> None:
    user_id, todo_id, _ = _seed_todo(db_session)
    with (
        patch(
            "api.services.application_packet_service.propose_application_packet",
            return_value=_mock_proposal(),
        ),
        patch(
            "api.services.application_packet_service.resume_service.tailor",
            return_value=_mock_tailor(),
        ),
        patch(
            "api.services.application_packet_service.draft_cover_letter",
            return_value=_mock_cover_letter(),
        ),
    ):
        application_packet_service.generate(db_session, user_id, todo_id)

    updated = application_packet_service.patch(
        db_session,
        user_id,
        todo_id,
        ApplicationPacketPatchRequest(
            answers=[
                PacketAnswerPatchItem(
                    key="work_authorization",
                    status=PacketAnswerStatus.confirmed,
                    final_answer="Yes, authorized.",
                )
            ],
            fit_verdict="apply",
        ),
    )
    assert updated is not None
    work_auth = next(a for a in updated.answers if a.key == "work_authorization")
    assert work_auth.status == PacketAnswerStatus.confirmed
    assert work_auth.final_answer == "Yes, authorized."
    assert updated.fit_verdict == "apply"


def test_open_marks_packet_opened_and_returns_apply_url(db_session: Session) -> None:
    user_id, todo_id, _ = _seed_todo(db_session)
    with (
        patch(
            "api.services.application_packet_service.propose_application_packet",
            return_value=_mock_proposal(),
        ),
        patch(
            "api.services.application_packet_service.resume_service.tailor",
            return_value=_mock_tailor(),
        ),
        patch(
            "api.services.application_packet_service.draft_cover_letter",
            return_value=_mock_cover_letter(),
        ),
    ):
        packet = application_packet_service.generate(db_session, user_id, todo_id)

    opened = application_packet_service.open(db_session, user_id, todo_id)

    assert opened.packet_id == packet.id
    assert opened.apply_url == packet.apply_url
    assert opened.todo_item_id == todo_id

    refreshed = application_packet_service.get(db_session, user_id, todo_id)
    assert refreshed is not None
    assert refreshed.status == "opened"


def test_generate_does_not_include_screening_answers(db_session: Session) -> None:
    user_id, todo_id, _ = _seed_todo(db_session)
    with (
        patch(
            "api.services.application_packet_service.propose_application_packet",
            return_value=_mock_proposal(),
        ),
        patch(
            "api.services.application_packet_service.resume_service.tailor",
            return_value=_mock_tailor(),
        ),
        patch(
            "api.services.application_packet_service.draft_cover_letter",
            return_value=_mock_cover_letter(),
        ),
    ):
        packet = application_packet_service.generate(db_session, user_id, todo_id)

    assert packet.answers == []


def test_generate_sets_default_label_from_job_title(db_session: Session) -> None:
    user_id, todo_id, _ = _seed_todo(db_session)
    with (
        patch(
            "api.services.application_packet_service.propose_application_packet",
            return_value=_mock_proposal(),
        ),
        patch(
            "api.services.application_packet_service.resume_service.tailor",
            return_value=_mock_tailor(),
        ),
        patch(
            "api.services.application_packet_service.draft_cover_letter",
            return_value=_mock_cover_letter(),
        ),
    ):
        packet = application_packet_service.generate(db_session, user_id, todo_id)

    assert packet.label == "Platform Engineer"
    assert packet.title == "Platform Engineer"
    assert packet.company == "Globex"


def test_get_and_rename_packet_by_id(db_session: Session) -> None:
    user_id, todo_id, _ = _seed_todo(db_session)
    with (
        patch(
            "api.services.application_packet_service.propose_application_packet",
            return_value=_mock_proposal(),
        ),
        patch(
            "api.services.application_packet_service.resume_service.tailor",
            return_value=_mock_tailor(),
        ),
        patch(
            "api.services.application_packet_service.draft_cover_letter",
            return_value=_mock_cover_letter(),
        ),
    ):
        generated = application_packet_service.generate(db_session, user_id, todo_id)

    fetched = application_packet_service.get_by_id(db_session, user_id, generated.id)
    assert fetched is not None
    assert fetched.id == generated.id

    renamed = application_packet_service.patch_by_id(
        db_session,
        user_id,
        generated.id,
        ApplicationPacketPatchRequest(label="Office Manager"),
    )
    assert renamed is not None
    assert renamed.label == "Office Manager"


def test_reuse_copies_cover_letter(db_session: Session) -> None:
    user_id, source_todo_id, _ = _seed_todo(db_session)
    _, target_todo_id, _ = _seed_todo(db_session)
    with (
        patch(
            "api.services.application_packet_service.propose_application_packet",
            return_value=_mock_proposal(),
        ),
        patch(
            "api.services.application_packet_service.resume_service.tailor",
            return_value=_mock_tailor(),
        ),
        patch(
            "api.services.application_packet_service.draft_cover_letter",
            return_value=_mock_cover_letter(),
        ),
    ):
        source = application_packet_service.generate(db_session, user_id, source_todo_id)
        application_packet_service.patch(
            db_session,
            user_id,
            source_todo_id,
            ApplicationPacketPatchRequest(label="Office Manager"),
        )

    reused = application_packet_service.reuse_from(
        db_session, user_id, target_todo_id, source.id
    )
    assert reused.cover_letter == source.cover_letter
    assert reused.answers == []
    assert reused.label == "Office Manager"


def test_list_prepared_includes_label(db_session: Session) -> None:
    user_id, todo_id, _ = _seed_todo(db_session)
    with (
        patch(
            "api.services.application_packet_service.propose_application_packet",
            return_value=_mock_proposal(),
        ),
        patch(
            "api.services.application_packet_service.resume_service.tailor",
            return_value=_mock_tailor(),
        ),
        patch(
            "api.services.application_packet_service.draft_cover_letter",
            return_value=_mock_cover_letter(),
        ),
    ):
        generated = application_packet_service.generate(db_session, user_id, todo_id)
        application_packet_service.patch_by_id(
            db_session,
            user_id,
            generated.id,
            ApplicationPacketPatchRequest(label="Sales Manager"),
        )

    listed = application_packet_service.list_prepared(db_session, user_id)
    assert listed.total == 1
    assert listed.items[0].label == "Sales Manager"
    assert listed.items[0].id == generated.id

