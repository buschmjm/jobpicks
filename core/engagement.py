"""Engagement helpers — streaks, milestones, activity recording."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.models import TodoItem, TodoStatus, UserEngagement

MILESTONE_DEFINITIONS: dict[str, str] = {
    "first_prep": "First application prepped",
    "first_applied": "First application submitted",
    "five_applied": "5 applications sent",
    "streak_3": "3-day streak",
    "streak_7": "7-day streak",
    "streak_14": "14-day streak",
}

ACTIVITY_TYPES = frozenset(
    {
        "session",
        "deck_swipe",
        "prepare_open",
        "mark_applied",
        "advisor_message",
        "resume_session",
    }
)


def _today() -> date:
    return datetime.now(tz=UTC).date()


def _week_start() -> datetime:
    now = datetime.now(tz=UTC)
    start = now - timedelta(days=now.weekday())
    return start.replace(hour=0, minute=0, second=0, microsecond=0)


def get_or_create_engagement(session: Session, user_id: UUID) -> UserEngagement:
    row = session.get(UserEngagement, user_id)
    if row is None:
        row = UserEngagement(user_id=user_id, milestones=[])
        session.add(row)
        session.flush()
    return row


def _update_streak(row: UserEngagement, today: date) -> None:
    if row.last_active_date is None:
        row.streak_days = 1
    elif row.last_active_date == today:
        return
    elif row.last_active_date == today - timedelta(days=1):
        row.streak_days += 1
    else:
        row.streak_days = 1
    row.last_active_date = today
    if row.streak_days > row.longest_streak:
        row.longest_streak = row.streak_days


def _award_milestone(row: UserEngagement, milestone_id: str) -> bool:
    milestones: list[str] = list(row.milestones or [])
    if milestone_id in milestones:
        return False
    milestones.append(milestone_id)
    row.milestones = milestones
    return True


def record_activity(session: Session, user_id: UUID, activity_type: str) -> list[str]:
    """Record user activity, update streak, return newly earned milestone ids."""
    if activity_type not in ACTIVITY_TYPES:
        raise ValueError(f"Unsupported activity type: {activity_type}")

    row = get_or_create_engagement(session, user_id)
    today = _today()
    _update_streak(row, today)

    new_milestones: list[str] = []
    if row.streak_days >= 3 and _award_milestone(row, "streak_3"):
        new_milestones.append("streak_3")
    if row.streak_days >= 7 and _award_milestone(row, "streak_7"):
        new_milestones.append("streak_7")
    if row.streak_days >= 14 and _award_milestone(row, "streak_14"):
        new_milestones.append("streak_14")

    if activity_type == "prepare_open" and _award_milestone(row, "first_prep"):
        new_milestones.append("first_prep")
    if activity_type == "mark_applied":
        if _award_milestone(row, "first_applied"):
            new_milestones.append("first_applied")
        applied_total = session.scalar(
            select(func.count())
            .select_from(TodoItem)
            .where(
                TodoItem.user_id == user_id,
                TodoItem.status == TodoStatus.APPLIED.value,
            )
        )
        if applied_total and applied_total >= 5 and _award_milestone(row, "five_applied"):
            new_milestones.append("five_applied")

    session.flush()
    return new_milestones


def engagement_stats(session: Session, user_id: UUID) -> dict[str, Any]:
    row = get_or_create_engagement(session, user_id)
    week_start = _week_start()

    applied_this_week = session.scalar(
        select(func.count())
        .select_from(TodoItem)
        .where(
            TodoItem.user_id == user_id,
            TodoItem.status == TodoStatus.APPLIED.value,
            TodoItem.applied_at.is_not(None),
            TodoItem.applied_at >= week_start,
        )
    )
    applied_total = session.scalar(
        select(func.count())
        .select_from(TodoItem)
        .where(
            TodoItem.user_id == user_id,
            TodoItem.status == TodoStatus.APPLIED.value,
        )
    )
    in_prep_count = session.scalar(
        select(func.count())
        .select_from(TodoItem)
        .where(
            TodoItem.user_id == user_id,
            TodoItem.status == TodoStatus.TO_APPLY.value,
        )
    )

    milestones = list(row.milestones or [])
    return {
        "streak_days": row.streak_days,
        "longest_streak": row.longest_streak,
        "applied_this_week": int(applied_this_week or 0),
        "applied_total": int(applied_total or 0),
        "in_prep_count": int(in_prep_count or 0),
        "milestones": [
            {"id": mid, "label": MILESTONE_DEFINITIONS.get(mid, mid)} for mid in milestones
        ],
    }
