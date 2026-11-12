"""Engagement API service."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from core.engagement import engagement_stats, record_activity
from core.entitlements import SubscriptionStatus, is_pro_active
from core.models import TodoItem, TodoStatus, User, UserJobQueue
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.repositories.todo_repo import TodoRepository
from api.services.todo_service import todo_item_from_orm


def _queue_score(session: Session, user_id: UUID, job_id: UUID) -> float | None:
    row = session.scalar(
        select(UserJobQueue.score)
        .where(UserJobQueue.user_id == user_id)
        .where(UserJobQueue.job_id == job_id)
        .order_by(UserJobQueue.score.desc().nullslast())
        .limit(1)
    )
    return float(row) if row is not None else None


def _focus_job(session: Session, user_id: UUID) -> dict[str, Any] | None:
    repo = TodoRepository(session)
    items = repo.list_items(user_id, TodoStatus.TO_APPLY.value)
    if not items:
        return None

    best_item = items[0]
    best_score = _queue_score(session, user_id, best_item.job_id)
    for item in items[1:]:
        score = _queue_score(session, user_id, item.job_id)
        if score is not None and (best_score is None or score > best_score):
            best_score = score
            best_item = item

    schema = todo_item_from_orm(best_item, queue_score=best_score)
    return {
        "id": str(schema.id),
        "title": schema.title,
        "company": schema.company,
        "match_score": schema.match_score,
    }


def get_engagement_summary(session: Session, user: User) -> dict[str, Any]:
    stats = engagement_stats(session, user_id=user.id)
    focus = _focus_job(session, user.id)

    trial_active = False
    trial_ends_at = None
    if user.subscription_status == SubscriptionStatus.TRIALING.value and is_pro_active(user):
        trial_active = True
        trial_ends_at = user.subscription_period_end

    return {
        **stats,
        "focus_job": focus,
        "pro_trial_active": trial_active,
        "pro_trial_ends_at": trial_ends_at.isoformat() if trial_ends_at else None,
    }


def heartbeat(session: Session, user_id: UUID, activity_type: str = "session") -> dict[str, Any]:
    new_milestones = record_activity(session, user_id, activity_type)
    user = session.get(User, user_id)
    if user is None:
        raise ValueError("User not found")
    summary = get_engagement_summary(session, user)
    summary["new_milestones"] = new_milestones
    return summary


def start_pro_trial(session: Session, user: User, *, days: int = 3) -> None:
    """Grant a short Pro preview for new free users after onboarding."""
    from datetime import UTC, datetime, timedelta

    from core.entitlements import PlanTier

    if user.stripe_subscription_id:
        return
    if user.plan_tier == PlanTier.PRO.value and is_pro_active(user):
        return
    now = datetime.now(tz=UTC)
    user.plan_tier = PlanTier.PRO.value
    user.subscription_status = SubscriptionStatus.TRIALING.value
    user.subscription_period_end = now + timedelta(days=days)
    session.flush()


engagement_service = type(
    "EngagementService",
    (),
    {
        "get_summary": staticmethod(get_engagement_summary),
        "heartbeat": staticmethod(heartbeat),
        "start_pro_trial": staticmethod(start_pro_trial),
    },
)()
