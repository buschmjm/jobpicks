"""WS-4 packet lifetime entitlement tests."""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest
from api.repositories.application_packet_repo import ApplicationPacketRepository
from api.repositories.todo_repo import TodoRepository
from api.services.application_packet_service import application_packet_service
from core.entitlements import FREE_LIFETIME_PACKET_LIMIT, PlanTier
from core.models import ApplicationPacketStatus, Job, JobStatus, RemoteMode, User
from core.packet_entitlements import (
    PacketLimitExceeded,
    can_generate_packet,
    ensure_can_generate_packet,
    lifetime_packets_used,
)
from sqlalchemy.orm import Session


def _seed_job(db_session: Session, *, suffix: str | None = None) -> Job:
    token = suffix or str(uuid4())
    job = Job(
        company_name="Acme",
        title="Engineer",
        normalized_title="engineer",
        canonical_hash=f"hash-{token}",
        status=JobStatus.OPEN,
        remote_mode=RemoteMode.REMOTE,
        description="Build things.",
        source_url=f"https://example.com/jobs/{token}",
        apply_url=f"https://boards.greenhouse.io/acme/jobs/{token}",
        ats_type="greenhouse",
        primary_source="test",
    )
    db_session.add(job)
    db_session.flush()
    return job


def _free_user(db_session: Session) -> User:
    user = User(email=f"free-{uuid4()}@example.com", plan_tier=PlanTier.FREE.value)
    db_session.add(user)
    db_session.flush()
    return user


def _packet_row(
    db_session: Session,
    *,
    user_id,
    todo_item_id,
    job_id,
    status: ApplicationPacketStatus = ApplicationPacketStatus.READY,
) -> None:
    ApplicationPacketRepository(db_session).create(
        user_id=user_id,
        todo_item_id=todo_item_id,
        job_id=job_id,
        apply_url="https://boards.greenhouse.io/acme/jobs/1",
        status=status,
    )
    db_session.commit()


def test_lifetime_packets_used_counts_generating_ready_opened(db_session: Session) -> None:
    user = _free_user(db_session)
    job_a = _seed_job(db_session, suffix="a")
    job_b = _seed_job(db_session, suffix="b")
    todo_a = TodoRepository(db_session).create(user.id, job_a.id)
    todo_b = TodoRepository(db_session).create(user.id, job_b.id)
    db_session.commit()

    _packet_row(
        db_session,
        user_id=user.id,
        todo_item_id=todo_a.id,
        job_id=job_a.id,
        status=ApplicationPacketStatus.READY,
    )
    _packet_row(
        db_session,
        user_id=user.id,
        todo_item_id=todo_b.id,
        job_id=job_b.id,
        status=ApplicationPacketStatus.GENERATING,
    )

    assert lifetime_packets_used(db_session, user.id) == 2


def test_free_user_blocked_at_packet_limit(db_session: Session) -> None:
    user = _free_user(db_session)
    for index in range(FREE_LIFETIME_PACKET_LIMIT):
        job = _seed_job(db_session, suffix=f"free-{index}")
        todo = TodoRepository(db_session).create(user.id, job.id)
        db_session.commit()
        _packet_row(db_session, user_id=user.id, todo_item_id=todo.id, job_id=job.id)

    new_job = _seed_job(db_session, suffix="blocked")
    new_todo = TodoRepository(db_session).create(user.id, new_job.id)
    db_session.commit()

    assert can_generate_packet(db_session, user, new_todo.id) is False
    with pytest.raises(PacketLimitExceeded):
        ensure_can_generate_packet(db_session, user, new_todo.id)


def test_regenerate_existing_todo_allowed_at_limit(db_session: Session) -> None:
    user = _free_user(db_session)
    job_a = _seed_job(db_session, suffix="regen-a")
    job_b = _seed_job(db_session, suffix="regen-b")
    todo = TodoRepository(db_session).create(user.id, job_a.id)
    db_session.commit()
    _packet_row(db_session, user_id=user.id, todo_item_id=todo.id, job_id=job_a.id)

    other_todo = TodoRepository(db_session).create(user.id, job_b.id)
    db_session.commit()
    _packet_row(db_session, user_id=user.id, todo_item_id=other_todo.id, job_id=job_b.id)

    assert can_generate_packet(db_session, user, todo.id) is True


def test_pro_user_monthly_packet_limit(db_session: Session) -> None:
    from core.entitlements import PRO_PACKETS_PER_MONTH

    user = User(
        email=f"pro-{uuid4()}@example.com",
        plan_tier=PlanTier.PRO.value,
        subscription_status="active",
    )
    db_session.add(user)
    db_session.flush()
    for index in range(PRO_PACKETS_PER_MONTH):
        job = _seed_job(db_session, suffix=f"pro-{index}")
        todo = TodoRepository(db_session).create(user.id, job.id)
        db_session.commit()
        _packet_row(db_session, user_id=user.id, todo_item_id=todo.id, job_id=job.id)

    new_job = _seed_job(db_session, suffix="pro-new")
    new_todo = TodoRepository(db_session).create(user.id, new_job.id)
    db_session.commit()
    assert can_generate_packet(db_session, user, new_todo.id) is False


def test_request_generate_raises_at_limit(db_session: Session) -> None:
    user = _free_user(db_session)
    todos = []
    for index in range(2):
        job = _seed_job(db_session, suffix=f"req-{index}")
        todo = TodoRepository(db_session).create(user.id, job.id)
        db_session.commit()
        todos.append((todo, job))
    for todo, job in todos:
        _packet_row(db_session, user_id=user.id, todo_item_id=todo.id, job_id=job.id)

    blocked_job = _seed_job(db_session, suffix="req-blocked")
    blocked_todo = TodoRepository(db_session).create(user.id, blocked_job.id)
    db_session.commit()

    with pytest.raises(PacketLimitExceeded):
        with patch("api.services.application_packet_service.enqueue_job"):
            application_packet_service.request_generate(db_session, user.id, blocked_todo.id)


def test_execute_generate_raises_at_limit(db_session: Session) -> None:
    user = _free_user(db_session)
    todos = []
    for index in range(2):
        job = _seed_job(db_session, suffix=f"exec-{index}")
        todo = TodoRepository(db_session).create(user.id, job.id)
        db_session.commit()
        todos.append((todo, job))
    for todo, job in todos:
        _packet_row(db_session, user_id=user.id, todo_item_id=todo.id, job_id=job.id)

    blocked_job = _seed_job(db_session, suffix="exec-blocked")
    blocked_todo = TodoRepository(db_session).create(user.id, blocked_job.id)
    db_session.commit()

    with pytest.raises(PacketLimitExceeded):
        with patch("api.services.application_packet_service.enqueue_job"):
            application_packet_service.request_generate(db_session, user.id, blocked_todo.id)
