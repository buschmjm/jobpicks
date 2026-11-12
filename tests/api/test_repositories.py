"""Repository unit tests against SQLite."""

from __future__ import annotations

import uuid

from api.repositories.deck_repo import DeckRepository
from api.repositories.events_repo import EventsRepository
from api.repositories.profile_repo import ProfileRepository
from api.repositories.todo_repo import TodoRepository
from api.repositories.user_repo import UserRepository
from api.schemas import FactStatus, ProfileFact, QuestionnaireRequest
from core.models import (
    EventType,
    Job,
    JobStatus,
    QueueState,
    RemoteMode,
    UserJobQueue,
)
from sqlalchemy.orm import Session


def _seed_job(session: Session) -> uuid.UUID:
    job = Job(
        company_name="Acme Corp",
        title="Platform Engineer",
        normalized_title="platform engineer",
        canonical_hash="hash-1",
        status=JobStatus.OPEN,
        remote_mode=RemoteMode.REMOTE,
        source_url="https://example.com/jobs/1",
        primary_source="test",
    )
    session.add(job)
    session.flush()
    return job.id


def test_user_repo_get_or_create(db_session: Session) -> None:
    repo = UserRepository(db_session)
    user = repo.get_or_create_by_email("dev@example.com")
    db_session.commit()
    again = repo.get_or_create_by_email("dev@example.com")
    assert user.id == again.id
    assert user.email == "dev@example.com"


def test_profile_repo_onboarding_flow(db_session: Session) -> None:
    user = UserRepository(db_session).get_or_create_by_email("onboard@example.com")
    db_session.commit()
    profiles = ProfileRepository(db_session)

    assert profiles.is_onboarding_complete(user.id) is False

    profiles.save_confirmed_facts(
        user.id,
        [ProfileFact(key="title", value="Engineer", status=FactStatus.confirmed)],
    )
    db_session.commit()
    assert profiles.is_onboarding_complete(user.id) is False

    profiles.save_questionnaire(
        user.id,
        QuestionnaireRequest(
            target_titles=["Platform Engineer"],
            min_salary=120_000,
            locations=["Austin, TX"],
            remote_preference="remote",
        ),
    )
    db_session.commit()
    assert profiles.is_onboarding_complete(user.id) is True


def test_deck_repo_queue_crud(db_session: Session) -> None:
    user = UserRepository(db_session).get_or_create_by_email("deck@example.com")
    job_id = _seed_job(db_session)
    db_session.add(
        UserJobQueue(user_id=user.id, job_id=job_id, score=0.82, state=QueueState.QUEUED.value)
    )
    db_session.commit()

    deck = DeckRepository(db_session)
    assert deck.count_queued(user.id) == 1
    item = deck.get_next_queued(user.id)
    assert item is not None
    assert item.job is not None
    assert item.job.title == "Platform Engineer"


def test_deck_repo_serves_highest_score_first(db_session: Session) -> None:
    user = UserRepository(db_session).get_or_create_by_email("deck-order@example.com")
    low_job = Job(
        company_name="Acme",
        title="Low Match",
        normalized_title="low match",
        canonical_hash="hash-low",
        status=JobStatus.OPEN,
        remote_mode=RemoteMode.REMOTE,
        source_url="https://example.com/low",
        primary_source="test",
    )
    high_job = Job(
        company_name="Beta",
        title="High Match",
        normalized_title="high match",
        canonical_hash="hash-high",
        status=JobStatus.OPEN,
        remote_mode=RemoteMode.REMOTE,
        source_url="https://example.com/high",
        primary_source="test",
    )
    db_session.add_all([low_job, high_job])
    db_session.flush()
    db_session.add_all(
        [
            UserJobQueue(user_id=user.id, job_id=low_job.id, score=0.35, state=QueueState.QUEUED.value),
            UserJobQueue(user_id=user.id, job_id=high_job.id, score=0.85, state=QueueState.QUEUED.value),
        ]
    )
    db_session.commit()

    item = DeckRepository(db_session).get_next_queued(user.id)
    assert item is not None
    assert item.job is not None
    assert item.job.title == "High Match"


def test_todo_repo_create_and_list(db_session: Session) -> None:
    user = UserRepository(db_session).get_or_create_by_email("todo@example.com")
    job_id = _seed_job(db_session)
    db_session.commit()

    todos = TodoRepository(db_session)
    item = todos.create(user.id, job_id)
    db_session.commit()
    listed = todos.list_items(user.id)
    assert len(listed) == 1
    assert listed[0].id == item.id


def test_events_repo_append_only(db_session: Session) -> None:
    user = UserRepository(db_session).get_or_create_by_email("events@example.com")
    db_session.commit()

    events = EventsRepository(db_session)
    row = events.append(EventType.LOGIN, user_id=user.id, payload={"email": user.email})
    db_session.commit()
    assert row.type == EventType.LOGIN.value
    assert row.user_id == user.id
