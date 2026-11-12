"""Engagement API — streaks, progress stats, activity heartbeat."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.deps import DbSession, get_current_user
from api.repositories.user_repo import UserRepository
from api.schemas import SessionUser
from api.services.engagement_service import engagement_service
from core.engagement import ACTIVITY_TYPES

router = APIRouter(prefix="/engagement", tags=["engagement"])


class FocusJobResponse(BaseModel):
    id: str
    title: str
    company: str
    match_score: int | None = None


class MilestoneResponse(BaseModel):
    id: str
    label: str


class EngagementSummaryResponse(BaseModel):
    streak_days: int = 0
    longest_streak: int = 0
    applied_this_week: int = 0
    applied_total: int = 0
    in_prep_count: int = 0
    milestones: list[MilestoneResponse] = Field(default_factory=list)
    focus_job: FocusJobResponse | None = None
    pro_trial_active: bool = False
    pro_trial_ends_at: str | None = None
    new_milestones: list[str] = Field(default_factory=list)


class HeartbeatRequest(BaseModel):
    activity_type: str = "session"


@router.get("/summary", response_model=EngagementSummaryResponse)
def engagement_summary(
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> EngagementSummaryResponse:
    row = UserRepository(db).get_by_id(user.id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    data = engagement_service.get_summary(db, row)
    return EngagementSummaryResponse(**data)


@router.post("/heartbeat", response_model=EngagementSummaryResponse)
def engagement_heartbeat(
    body: HeartbeatRequest,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> EngagementSummaryResponse:
    if body.activity_type not in ACTIVITY_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported activity type: {body.activity_type}",
        )
    data = engagement_service.heartbeat(db, user.id, body.activity_type)
    db.commit()
    return EngagementSummaryResponse(**data)
