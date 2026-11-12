"""Skill directory — search existing skills or create a new one."""

from __future__ import annotations

from core.models import Skill
from core.skill_directory import get_or_create_skill, search_skills
from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.deps import DbSession, get_current_user
from api.schemas import SessionUser, SkillCreateRequest, SkillOut, SkillSearchResponse

router = APIRouter(prefix="/skills", tags=["skills"])


def skill_to_out(skill: Skill) -> SkillOut:
    return SkillOut(
        id=skill.id,
        name=skill.name,
        normalized_name=skill.normalized_name,
        use_count=skill.use_count,
    )


@router.get("", response_model=SkillSearchResponse)
def search_skill_directory(
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
    q: str = Query(default="", max_length=80),
    limit: int = Query(default=20, ge=1, le=40),
) -> SkillSearchResponse:
    _ = user
    items = [skill_to_out(skill) for skill in search_skills(db, q, limit=limit)]
    return SkillSearchResponse(items=items, query=q)


@router.post("", response_model=SkillOut)
def create_skill(
    body: SkillCreateRequest,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> SkillOut:
    skill = get_or_create_skill(db, body.name, created_by_user_id=user.id)
    if skill is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Skill name is too short",
        )
    db.commit()
    db.refresh(skill)
    return skill_to_out(skill)
