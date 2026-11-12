"""Authenticated resume profile (experience + education)."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from api.deps import DbSession, get_current_user
from api.schemas import (
    ProfileResumeResponse,
    ProfileResumeUpdateRequest,
    ProfileResumeUpdateResponse,
    ProfileResumeUploadResponse,
    SessionUser,
)
from api.services.onboarding_service import ALLOWED_RESUME_TYPES, MAX_RESUME_BYTES
from api.services.profile_service import profile_service

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/resume", response_model=ProfileResumeResponse)
async def get_resume(
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> ProfileResumeResponse:
    return profile_service.get_resume(db, user.id)


@router.put("/resume", response_model=ProfileResumeUpdateResponse)
async def update_resume(
    body: ProfileResumeUpdateRequest,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> ProfileResumeUpdateResponse:
    return profile_service.update_resume(db, user.id, body)


@router.post("/resume/upload", response_model=ProfileResumeUploadResponse)
async def upload_resume(
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
    file: UploadFile = File(...),
) -> ProfileResumeUploadResponse:
    """Re-upload a PDF/DOCX resume and replace stored work experience + education."""
    content_type = file.content_type or "application/octet-stream"
    filename = file.filename or "resume"
    name = filename.lower()
    if content_type not in ALLOWED_RESUME_TYPES and not (
        name.endswith(".pdf") or name.endswith(".docx")
    ):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Resume must be PDF or DOCX",
        )

    data = await file.read()
    if len(data) > MAX_RESUME_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Resume exceeds 5MB limit",
        )

    try:
        return profile_service.import_resume_file(
            db,
            user.id,
            filename=filename,
            content_type=content_type,
            data=data,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
