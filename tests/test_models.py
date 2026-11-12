"""Smoke tests for SQLAlchemy models and schema metadata."""

from __future__ import annotations

import uuid

from core.database import Base
from sqlalchemy import inspect

from core import models

EXPECTED_TABLES = {
    "users",
    "profiles",
    "hard_constraints",
    "preference_weights",
    "companies",
    "jobs",
    "job_sources",
    "user_job_queue",
    "todo_items",
    "search_terms",
    "feedback_events",
    "events",
    "scoring_config",
    "digests",
    "referral_redemptions",
    "queue_jobs",
    "skills",
    "skill_aliases",
    "profile_skills",
    "job_skills",
}


def test_all_v1_tables_registered() -> None:
    assert EXPECTED_TABLES.issubset(set(Base.metadata.tables.keys()))


def test_models_import_and_instantiate() -> None:
    user = models.User(email="test@example.com")
    assert user.email == "test@example.com"
    assert user.id is None or isinstance(user.id, uuid.UUID)

    models.Company(name="Acme Corp", normalized_name="acme corp")
    job = models.Job(
        company_name="Acme Corp",
        title="Platform Engineer",
        normalized_title="platform engineer",
        canonical_hash="abc123",
        status=models.JobStatus.OPEN,
        remote_mode=models.RemoteMode.UNKNOWN,
    )
    assert job.status == models.JobStatus.OPEN
    assert job.remote_mode == models.RemoteMode.UNKNOWN

    queue_item = models.UserJobQueue(
        user_id=user.id or uuid.uuid4(),
        job_id=job.id or uuid.uuid4(),
        slot_type=models.QueueSlotType.CORE,
        state=models.QueueState.QUEUED,
    )
    assert queue_item.slot_type == models.QueueSlotType.CORE
    assert queue_item.state == models.QueueState.QUEUED

    todo = models.TodoItem(
        user_id=user.id or uuid.uuid4(),
        job_id=job.id or uuid.uuid4(),
        status=models.TodoStatus.TO_APPLY,
    )
    assert todo.status == models.TodoStatus.TO_APPLY


def test_event_type_enum_is_closed_set() -> None:
    assert len(models.EventType) == 23
    assert models.EventType.SWIPE_RIGHT.value == "swipe_right"
    assert models.EventType.UNSUBSCRIBED.value == "unsubscribed"
    assert models.EventType.DECK_OPENED.value == "deck_opened"


def test_job_has_vector_embedding_column() -> None:
    embedding_col = models.Job.__table__.c.embedding
    assert embedding_col.type.dim == 768  # type: ignore[attr-defined]


def test_foreign_keys_wired() -> None:
    mapper = inspect(models.UserJobQueue)
    fk_targets = {fk.target_fullname for fk in mapper.tables[0].foreign_keys}
    assert "users.id" in fk_targets
    assert "jobs.id" in fk_targets


def test_scoring_config_uses_string_primary_key() -> None:
    assert list(models.ScoringConfig.__table__.primary_key.columns)[0].name == "key"
