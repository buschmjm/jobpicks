"""Resume builder and job-tailored draft endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse

from api.deps import DbSession, get_current_user
from api.schemas import (
    ResumeDraftResponse,
    ResumeDraftUpdateRequest,
    ResumeTailorRequest,
    ResumeTailorResponse,
    SessionUser,
)
from api.services.resume_service import resume_service

router = APIRouter(prefix="/resume", tags=["resume"])


@router.post("/master", response_model=ResumeDraftResponse)
async def build_master_resume(
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> ResumeDraftResponse:
    return resume_service.build_master(db, user.id)


@router.post("/tailor", response_model=ResumeTailorResponse)
async def tailor_resume(
    body: ResumeTailorRequest,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> ResumeTailorResponse:
    return resume_service.tailor(db, user.id, body)


@router.get("/drafts/{draft_id}", response_model=ResumeDraftResponse)
async def get_draft(
    draft_id: UUID,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> ResumeDraftResponse:
    try:
        return resume_service.get_draft(db, user.id, draft_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.put("/drafts/{draft_id}", response_model=ResumeDraftResponse)
async def update_draft(
    draft_id: UUID,
    body: ResumeDraftUpdateRequest,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> ResumeDraftResponse:
    try:
        return resume_service.update_draft(
            db,
            user.id,
            draft_id,
            body.document,
            status=body.status,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/drafts/{draft_id}/accept", response_model=ResumeDraftResponse)
async def accept_draft(
    draft_id: UUID,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> ResumeDraftResponse:
    try:
        return resume_service.accept_draft(db, user.id, draft_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/drafts/{draft_id}/html", response_class=HTMLResponse)
async def render_draft_html(
    draft_id: UUID,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> HTMLResponse:
    try:
        html = resume_service.render_html(db, user.id, draft_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to render resume HTML: {exc}",
        ) from exc
    return HTMLResponse(content=html)
