"""Privacy service: delete-my-data and resume file cleanup."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from core.models import (
    ApplicationPacket,
    Digest,
    Event,
    FeedbackEvent,
    HardConstraints,
    PreferenceWeights,
    Profile,
    SavedApplicationAnswer,
    TodoItem,
    User,
    UserJobQueue,
)
from core.privacy import (
    anonymized_user_email,
    event_anonymize_cutoff,
    find_stale_resume_files,
    resume_storage_cutoff,
    scrub_event_payload,
    should_anonymize_event,
)
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import Executable

logger = logging.getLogger(__name__)


def resume_storage_dir() -> Path | None:
    raw = os.environ.get("RESUME_STORAGE_DIR", "").strip()
    if not raw:
        return None
    return Path(raw)


def delete_resume_files_for_user(user_id: UUID) -> int:
    """Remove any stored resume files for a user (immediate on deletion)."""
    storage = resume_storage_dir()
    if storage is None or not storage.is_dir():
        return 0

    removed = 0
    prefix = f"{user_id}_"
    for path in storage.iterdir():
        if path.is_file() and path.name.startswith(prefix):
            path.unlink(missing_ok=True)
            removed += 1
    return removed


def _execute_rowcount(session: Session, stmt: Executable) -> int:
    result = session.execute(stmt)
    rowcount = getattr(result, "rowcount", None)
    return int(rowcount) if rowcount is not None else 0


def delete_user_data(session: Session, user_id: UUID) -> dict[str, int]:
    """
    Hard-delete profile/resume, delete todo/queue rows, anonymize events.
    Deactivates the user account and replaces email with a deleted placeholder.
    """
    user = session.get(User, user_id)
    if user is None:
        return {"deleted": 0}

    counts = {
        "profiles": _execute_rowcount(session, delete(Profile).where(Profile.user_id == user_id)),
        "hard_constraints": _execute_rowcount(
            session, delete(HardConstraints).where(HardConstraints.user_id == user_id)
        ),
        "preference_weights": _execute_rowcount(
            session, delete(PreferenceWeights).where(PreferenceWeights.user_id == user_id)
        ),
        "todo_items": _execute_rowcount(
            session, delete(TodoItem).where(TodoItem.user_id == user_id)
        ),
        "queue_items": _execute_rowcount(
            session, delete(UserJobQueue).where(UserJobQueue.user_id == user_id)
        ),
        "feedback_events": _execute_rowcount(
            session, delete(FeedbackEvent).where(FeedbackEvent.user_id == user_id)
        ),
        "digests": _execute_rowcount(session, delete(Digest).where(Digest.user_id == user_id)),
        "saved_application_answers": _execute_rowcount(
            session, delete(SavedApplicationAnswer).where(SavedApplicationAnswer.user_id == user_id)
        ),
        "application_packets": _execute_rowcount(
            session, delete(ApplicationPacket).where(ApplicationPacket.user_id == user_id)
        ),
        "resume_files": delete_resume_files_for_user(user_id),
    }

    events = session.scalars(select(Event).where(Event.user_id == user_id)).all()
    anonymized_events = 0
    for event in events:
        event.user_id = None
        event.payload = scrub_event_payload(event.payload)
        anonymized_events += 1
    counts["events_anonymized"] = anonymized_events

    user.email = anonymized_user_email(user_id)
    user.is_active = False
    session.flush()

    logger.info("deleted user data user_id=%s counts=%s", user_id, counts)
    return counts


def export_user_data(session: Session, user_id: UUID) -> dict[str, object]:
    """GDPR Art. 15/20 portable export of user-held data."""
    user = session.get(User, user_id)
    if user is None:
        return {"error": "user_not_found"}

    profile = session.scalar(select(Profile).where(Profile.user_id == user_id))
    prefs = session.scalar(
        select(PreferenceWeights).where(
            PreferenceWeights.user_id == user_id,
            PreferenceWeights.is_current.is_(True),
        )
    )
    constraints = session.scalar(select(HardConstraints).where(HardConstraints.user_id == user_id))
    todos = session.scalars(select(TodoItem).where(TodoItem.user_id == user_id)).all()
    queue = session.scalars(select(UserJobQueue).where(UserJobQueue.user_id == user_id)).all()
    feedback = session.scalars(select(FeedbackEvent).where(FeedbackEvent.user_id == user_id)).all()
    vault = session.scalars(
        select(SavedApplicationAnswer).where(SavedApplicationAnswer.user_id == user_id)
    ).all()
    packets = session.scalars(
        select(ApplicationPacket).where(ApplicationPacket.user_id == user_id)
    ).all()

    return {
        "exported_at": datetime.now(tz=UTC).isoformat(),
        "user_id": str(user_id),
        "email": user.email,
        "profile": profile.parsed_resume if profile else None,
        "profile_fields": {
            "headline": profile.headline if profile else None,
            "summary": profile.summary if profile else None,
            "target_titles": profile.target_titles if profile else None,
            "skills": profile.skills if profile else None,
            "seniority_level": profile.seniority_level if profile else None,
        },
        "preferences": prefs.weights if prefs else None,
        "hard_constraints": {
            "min_salary": constraints.min_salary,
            "locations": constraints.locations,
            "max_commute_minutes": constraints.max_commute_minutes,
            "remote_openness": constraints.remote_openness,
            "never_industries": constraints.never_industries,
            "blocked_companies": constraints.blocked_companies,
        }
        if constraints
        else None,
        "todo_items": [
            {
                "id": str(item.id),
                "job_id": str(item.job_id),
                "status": item.status,
                "application_steps": item.application_steps,
                "applied_at": item.applied_at.isoformat() if item.applied_at else None,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in todos
        ],
        "queue_swipes": [
            {
                "job_id": str(row.job_id),
                "state": row.state,
                "slot_type": row.slot_type,
                "score": float(row.score) if row.score is not None else None,
            }
            for row in queue
        ],
        "feedback_events": [
            {
                "job_id": str(row.job_id) if row.job_id else None,
                "action": str(row.action),
                "reason": str(row.reason) if row.reason else None,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in feedback
        ],
        "saved_application_answers": [
            {
                "question_key": row.question_key,
                "question_text": row.question_text,
                "answer": row.answer,
            }
            for row in vault
        ],
        "application_packets": [
            {
                "todo_item_id": str(row.todo_item_id) if row.todo_item_id else None,
                "status": row.status,
                "fit_verdict": row.fit_verdict,
                "cover_letter": row.cover_letter,
            }
            for row in packets
        ],
    }


def purge_stale_resume_files(session: Session | None = None) -> int:
    """Delete resume files older than RESUME_FILE_MAX_AGE_DAYS."""
    _ = session  # reserved for future DB-backed resume metadata
    storage = resume_storage_dir()
    if storage is None:
        return 0

    cutoff = resume_storage_cutoff()
    removed = 0
    for stale in find_stale_resume_files(storage, cutoff):
        stale.path.unlink(missing_ok=True)
        removed += 1
    return removed


def anonymize_old_events(session: Session) -> int:
    """Anonymize analytics events past the retention window."""
    cutoff = event_anonymize_cutoff()
    events = session.scalars(select(Event).where(Event.user_id.is_not(None))).all()
    count = 0
    for event in events:
        if should_anonymize_event(event.created_at, cutoff):
            event.user_id = None
            event.payload = scrub_event_payload(event.payload)
            count += 1
    session.flush()
    return count
