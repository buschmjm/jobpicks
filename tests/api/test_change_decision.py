"""Tests for changing past swipe decisions."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from api.repositories.profile_repo import ProfileRepository
from api.schemas import QuestionnaireRequest, SwipeAction
from api.services.auth_service import auth_service
from api.services.deck_service import deck_service
from api.services.todo_service import todo_service
from core.models import Job, JobStatus, QueueState, RemoteMode, TodoStatus, UserJobQueue
from sqlalchemy.orm import Session


def _user_with_swiped_job(
    db_session: Session,
    *,
    state: QueueState = QueueState.SWIPED_LEFT,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    _, user_id = auth_service.verify_and_create_session(db_session, f"change-{state.value}@example.com")
    job = Job(
        company_name="Acme",
        title="Platform Engineer",
        normalized_title="platform engineer",
        canonical_hash=f"hash-{state.value}-{uuid.uuid4()}",
        status=JobStatus.OPEN,
        remote_mode=RemoteMode.REMOTE,
        description="Build platforms",
        source_url="https://example.com/pe",
    )
    db_session.add(job)
    db_session.flush()
    queue_item = UserJobQueue(
        user_id=user_id,
        job_id=job.id,
        score=0.8,
        state=state.value,
        swiped_at=datetime.now(UTC),
        explain={"why_bullets": ["Good fit"], "caution_bullets": []},
    )
    db_session.add(queue_item)
    db_session.commit()
    return user_id, job.id, queue_item.id


def test_change_decision_left_to_right_creates_todo(db_session: Session) -> None:
    user_id, job_id, queue_item_id = _user_with_swiped_job(db_session)
    ProfileRepository(db_session).save_questionnaire(
        user_id,
        QuestionnaireRequest(target_titles=["Platform Engineer"]),
    )
    db_session.commit()

    result = deck_service.change_decision(
        db_session,
        user_id,
        queue_item_id,
        SwipeAction.right,
        None,
    )
    assert result.success is True
    assert result.todo_item_id is not None

    items = todo_service.list_items(db_session, user_id)
    assert len(items) == 1
    assert items[0].job_id == job_id
    assert items[0].status == TodoStatus.TO_APPLY


def test_change_decision_right_to_left_archives_todo(db_session: Session) -> None:
    user_id, job_id, queue_item_id = _user_with_swiped_job(db_session, state=QueueState.SWIPED_RIGHT)
    ProfileRepository(db_session).save_questionnaire(
        user_id,
        QuestionnaireRequest(target_titles=["Platform Engineer"]),
    )
    db_session.commit()

    from api.schemas import MatchCard, WorkMode

    todo_service.ensure_apply_for_job(
        db_session,
        user_id,
        MatchCard(
            queue_item_id=queue_item_id,
            job_id=job_id,
            match_score=80,
            title="Platform Engineer",
            company="Acme",
            salary_display="salary not listed",
            work_mode=WorkMode.remote,
            location_display="Remote",
            posted_ago="1d ago",
            source="test",
            source_url="https://example.com/pe",
            description="",
        ),
    )
    db_session.commit()

    result = deck_service.change_decision(
        db_session,
        user_id,
        queue_item_id,
        SwipeAction.left,
        None,
    )
    assert result.success is True

    items = todo_service.list_items(db_session, user_id, TodoStatus.ARCHIVED)
    assert len(items) == 1


def test_change_decision_rejects_queued(db_session: Session) -> None:
    user_id, _, queue_item_id = _user_with_swiped_job(db_session, state=QueueState.QUEUED)

    result = deck_service.change_decision(
        db_session,
        user_id,
        queue_item_id,
        SwipeAction.right,
        None,
    )
    assert result.success is False
