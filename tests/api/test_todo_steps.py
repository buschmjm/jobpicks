"""Tests for todo application step tracking."""

from __future__ import annotations

import uuid

from api.repositories.profile_repo import ProfileRepository
from api.schemas import ApplicationStep, TodoStatus
from api.services.auth_service import auth_service
from api.services.todo_service import todo_service
from core.models import Job, JobStatus, RemoteMode
from sqlalchemy.orm import Session


def _user_with_job(db_session: Session) -> tuple[uuid.UUID, uuid.UUID]:
    _, user_id = auth_service.verify_and_create_session(
        db_session, f"steps-{uuid.uuid4()}@example.com"
    )
    job = Job(
        company_name="Acme",
        title="Platform Engineer",
        normalized_title="platform engineer",
        canonical_hash=f"hash-{uuid.uuid4()}",
        status=JobStatus.OPEN,
        remote_mode=RemoteMode.REMOTE,
        description="Build platforms",
        source_url="https://example.com/pe",
    )
    db_session.add(job)
    db_session.commit()
    return user_id, job.id


def test_new_todo_gets_default_application_steps(db_session: Session) -> None:
    user_id, job_id = _user_with_job(db_session)
    item = todo_service.create(db_session, user_id, job_id)
    assert item.steps_total == 4
    assert item.steps_done == 0
    assert any(step.label == "Review application packet" for step in item.application_steps)


def test_update_steps_persists_progress(db_session: Session) -> None:
    user_id, job_id = _user_with_job(db_session)
    created = todo_service.create(db_session, user_id, job_id)
    steps = [
        ApplicationStep(id=step.id, label=step.label, done=index == 0, order=step.order)
        for index, step in enumerate(created.application_steps)
    ]
    updated = todo_service.update_steps(db_session, user_id, created.id, steps)
    assert updated is not None
    assert updated.steps_done == 1
    assert updated.application_steps[0].done is True


def test_mark_applied_via_update_item(db_session: Session) -> None:
    user_id, job_id = _user_with_job(db_session)
    created = todo_service.create(db_session, user_id, job_id)
    updated = todo_service.update_item(
        db_session,
        user_id,
        created.id,
        status=TodoStatus.applied,
    )
    assert updated is not None
    assert updated.status == TodoStatus.applied
    assert updated.applied_selfreport_at is not None


def test_save_step_template_used_for_new_todos(db_session: Session) -> None:
    user_id, job_id = _user_with_job(db_session)
    template = [
        ApplicationStep(id="custom-1", label="Ask for referral", done=False, order=0),
        ApplicationStep(id="custom-2", label="Submit application", done=False, order=1),
    ]
    todo_service.save_step_template(db_session, user_id, template)

    item = todo_service.create(db_session, user_id, job_id)
    assert item.steps_total == 2
    assert item.application_steps[0].label == "Ask for referral"

    profile = ProfileRepository(db_session).get_profile(user_id)
    assert profile is not None
    assert profile.default_application_steps is not None
    assert len(profile.default_application_steps) == 2
