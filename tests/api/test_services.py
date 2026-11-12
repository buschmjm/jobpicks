"""Service-level tests with SQLite-backed repositories."""

from __future__ import annotations

import uuid

from api.auth import verify_session_token
from api.repositories.profile_repo import ProfileRepository
from api.schemas import QuestionnaireRequest, SwipeAction
from api.services.auth_service import auth_service
from api.services.deck_service import deck_service
from api.services.onboarding_service import onboarding_service
from core.models import Job, JobStatus, QueueState, RemoteMode, UserJobQueue
from sqlalchemy import select
from sqlalchemy.orm import Session


def _user_and_job(db_session: Session) -> tuple[uuid.UUID, uuid.UUID]:
    _, user_id = auth_service.verify_and_create_session(db_session, "swipe@example.com")
    job = Job(
        company_name="Acme",
        title="SRE",
        normalized_title="sre",
        canonical_hash="hash-swipe",
        status=JobStatus.OPEN,
        remote_mode=RemoteMode.REMOTE,
        description="Build infra",
        source_url="https://example.com/sre",
    )
    db_session.add(job)
    db_session.flush()
    db_session.add(
        UserJobQueue(
            user_id=user_id,
            job_id=job.id,
            score=0.75,
            state=QueueState.QUEUED.value,
            explain={"why_bullets": ["Good fit"], "caution_bullets": []},
        )
    )
    db_session.commit()
    return user_id, job.id


def test_auth_service_persists_user(db_session: Session) -> None:
    token, user_id = auth_service.verify_and_create_session(db_session, "auth@example.com")
    session = verify_session_token(token)
    assert session is not None
    assert session.user_id == user_id

    again_token, again_id = auth_service.verify_and_create_session(db_session, "auth@example.com")
    assert again_id == user_id
    assert again_token != token


def test_onboarding_enqueues_term_ingest(db_session: Session) -> None:
    _, user_id = auth_service.verify_and_create_session(db_session, "queue@example.com")
    onboarding_service.save_questionnaire(
        db_session,
        user_id,
        QuestionnaireRequest(target_titles=["Engineer"], min_salary=100_000),
    )
    from core.models import Profile, QueueJob

    jobs = db_session.scalars(select(QueueJob)).all()
    assert len(jobs) == 1
    assert jobs[0].job_type == "term_ingest"
    assert jobs[0].payload["user_id"] == str(user_id)
    assert jobs[0].payload["terms"] == ["Engineer"]

    profile = db_session.scalar(select(Profile).where(Profile.user_id == user_id))
    assert profile is not None
    assert profile.awaiting_deck_backfill is True


def test_deck_swipe_right_creates_todo(db_session: Session) -> None:
    user_id, _job_id = _user_and_job(db_session)
    ProfileRepository(db_session).save_questionnaire(
        user_id,
        QuestionnaireRequest(target_titles=["SRE"]),
    )
    db_session.commit()

    next_card = deck_service.get_next(db_session, user_id)
    assert next_card.card is not None

    result = deck_service.swipe(
        db_session,
        user_id,
        next_card.card.queue_item_id,
        SwipeAction.right,
        None,
        2500,
    )
    assert result.todo_item_id is not None
    assert result.next_available is False

    from api.services.todo_service import todo_service

    items = todo_service.list_items(db_session, user_id)
    assert len(items) == 1
    assert items[0].job_id == next_card.card.job_id
