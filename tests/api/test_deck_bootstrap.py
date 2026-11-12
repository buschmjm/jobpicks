"""Tests for deck bootstrap helpers."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from unittest.mock import patch

from api.repositories.profile_repo import ProfileRepository
from api.schemas import QuestionnaireRequest
from api.services.auth_service import auth_service
from api.services.deck_service import deck_service
from api.services.onboarding_service import onboarding_service
from core.deck_bootstrap import (
    ensure_corpus_ingest,
    fan_out_pending_backfills,
    has_global_job_pending,
    has_pending_backfill,
    open_job_count,
    queued_count,
    schedule_backfill_if_needed,
)
from core.models import Job, JobStatus, Profile, QueueJob, QueueJobStatus, RemoteMode
from sqlalchemy import select
from sqlalchemy.orm import Session
from workers.consumer import HANDLERS


def _open_job(**kwargs: object) -> Job:
    """Test job within the API posting retention window (SQLite-safe)."""
    defaults: dict[str, object] = {
        "company_name": "Acme",
        "title": "Engineer",
        "normalized_title": "engineer",
        "canonical_hash": f"hash-{uuid.uuid4().hex[:8]}",
        "status": JobStatus.OPEN,
        "remote_mode": RemoteMode.REMOTE,
        "source_url": "https://example.com/job",
        "date_posted": date.today(),
        "is_direct": False,
    }
    defaults.update(kwargs)
    return Job(**defaults)  # type: ignore[arg-type]


def test_open_job_count(db_session: Session) -> None:
    assert open_job_count(db_session) == 0
    db_session.add(
        _open_job(
            title="SRE",
            normalized_title="sre",
            canonical_hash="hash-open",
            source_url="https://example.com/1",
        )
    )
    db_session.commit()
    assert open_job_count(db_session) == 1


def test_schedule_backfill_when_corpus_exists(db_session: Session) -> None:
    token, user_id = auth_service.verify_and_create_session(db_session, "deck@example.com")
    ProfileRepository(db_session).save_questionnaire(
        user_id,
        QuestionnaireRequest(target_titles=["SRE"], min_salary=100_000),
    )
    db_session.add(
        _open_job(
            title="Platform Engineer",
            normalized_title="platform engineer",
            canonical_hash="hash-deck",
            source_url="https://example.com/2",
        )
    )
    db_session.commit()

    enqueued: list[QueueJob] = []

    def _enqueue(session, job_type, payload, *, priority=0):
        row = QueueJob(job_type=job_type, payload=payload, priority=priority)
        session.add(row)
        session.flush()
        enqueued.append(row)

    assert queued_count(db_session, user_id) == 0
    assert schedule_backfill_if_needed(db_session, user_id, enqueue=_enqueue) is True
    assert enqueued[0].job_type == "queue_backfill"
    assert enqueued[0].payload["user_id"] == str(user_id)


def test_deck_status_building_when_corpus_empty(db_session: Session) -> None:
    _, user_id = auth_service.verify_and_create_session(db_session, "build@example.com")
    onboarding_service.save_questionnaire(
        db_session,
        user_id,
        QuestionnaireRequest(target_titles=["Engineer"]),
    )
    status = deck_service.get_status(db_session, user_id)
    assert status.queue_remaining == 0
    assert status.building is True
    assert status.open_jobs == 0


def test_ensure_corpus_ingest_dedupes(db_session: Session) -> None:
    enqueued: list[QueueJob] = []

    def _enqueue(session, job_type, payload, *, priority=0):
        row = QueueJob(job_type=job_type, payload=payload, priority=priority)
        session.add(row)
        session.flush()
        enqueued.append(row)

    assert ensure_corpus_ingest(db_session, enqueue=_enqueue) is True
    assert ensure_corpus_ingest(db_session, enqueue=_enqueue) is False
    assert len(enqueued) == 1
    assert enqueued[0].job_type == "corpus_ingest"
    assert enqueued[0].payload == {}


def test_singleton_corpus_ingest_for_multiple_signups(db_session: Session) -> None:
    user_ids: list[uuid.UUID] = []
    for index in range(10):
        _, user_id = auth_service.verify_and_create_session(
            db_session, f"signup{index}@example.com"
        )
        onboarding_service.save_questionnaire(
            db_session,
            user_id,
            QuestionnaireRequest(target_titles=["Engineer"]),
        )
        user_ids.append(user_id)

    term_ingest_jobs = db_session.scalars(
        select(QueueJob).where(QueueJob.job_type == "term_ingest")
    ).all()
    ingest_jobs = db_session.scalars(
        select(QueueJob).where(QueueJob.job_type == "corpus_ingest")
    ).all()
    backfill_jobs = db_session.scalars(
        select(QueueJob).where(QueueJob.job_type == "queue_backfill")
    ).all()

    assert len(term_ingest_jobs) == 1
    assert term_ingest_jobs[0].payload["terms"] == ["Engineer"]
    assert len(ingest_jobs) == 1
    assert ingest_jobs[0].payload == {}
    assert len(backfill_jobs) == 9

    profiles = db_session.scalars(
        select(Profile).where(Profile.user_id.in_(user_ids))
    ).all()
    assert all(profile.awaiting_deck_backfill for profile in profiles)


def test_fan_out_pending_backfills(db_session: Session) -> None:
    user_ids: list[uuid.UUID] = []
    for email in ("a@example.com", "b@example.com"):
        _, user_id = auth_service.verify_and_create_session(db_session, email)
        profile = ProfileRepository(db_session).get_or_create_profile(user_id)
        profile.target_titles = ["Engineer"]
        profile.onboarding_completed_at = datetime.now(tz=UTC)
        profile.awaiting_deck_backfill = True
        user_ids.append(user_id)
    db_session.commit()

    enqueued: list[QueueJob] = []

    def _enqueue(session, job_type, payload, *, priority=0):
        row = QueueJob(job_type=job_type, payload=payload, priority=priority)
        session.add(row)
        session.flush()
        enqueued.append(row)

    count = fan_out_pending_backfills(db_session, enqueue=_enqueue)
    assert count == 2
    assert {job.payload["user_id"] for job in enqueued} == {str(uid) for uid in user_ids}


def test_schedule_backfill_rate_limited(db_session: Session) -> None:
    _, user_id = auth_service.verify_and_create_session(db_session, "rate@example.com")
    ProfileRepository(db_session).save_questionnaire(
        user_id,
        QuestionnaireRequest(target_titles=["Engineer"]),
    )
    db_session.add(
        _open_job(
            canonical_hash="hash-rate",
            source_url="https://example.com/rate",
        )
    )
    db_session.add(
        QueueJob(
            job_type="queue_backfill",
            payload={"user_id": str(user_id)},
            status=QueueJobStatus.COMPLETED.value,
            finished_at=datetime.now(tz=UTC),
        )
    )
    db_session.commit()

    enqueued: list[QueueJob] = []

    def _enqueue(session, job_type, payload, *, priority=0):
        row = QueueJob(job_type=job_type, payload=payload, priority=priority)
        session.add(row)
        enqueued.append(row)

    assert schedule_backfill_if_needed(db_session, user_id, enqueue=_enqueue) is False
    assert len(enqueued) == 0


def test_corpus_ingest_does_not_call_backfill_handler(db_session: Session) -> None:
    assert "corpus_ingest" in HANDLERS
    assert "bootstrap_ingest" not in HANDLERS

    with patch("ingest.runner.run_ingest", return_value={"inserted": 0}) as run_ingest:
        with patch(
            "workers.consumer.fan_out_pending_backfills", return_value=0
        ) as fan_out:
            HANDLERS["corpus_ingest"](db_session, {})
            run_ingest.assert_called_once()
            fan_out.assert_called_once()


def test_has_pending_backfill_filters_by_user(db_session: Session) -> None:
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    db_session.add(
        QueueJob(
            job_type="queue_backfill",
            payload={"user_id": str(user_a)},
            status=QueueJobStatus.PENDING.value,
        )
    )
    db_session.commit()

    assert has_pending_backfill(db_session, user_a) is True
    assert has_pending_backfill(db_session, user_b) is False


def test_has_global_job_pending(db_session: Session) -> None:
    db_session.add(
        QueueJob(
            job_type="corpus_ingest",
            payload={},
            status=QueueJobStatus.RUNNING.value,
        )
    )
    db_session.commit()
    assert has_global_job_pending(db_session, "corpus_ingest") is True
    assert has_global_job_pending(db_session, "queue_backfill") is False
