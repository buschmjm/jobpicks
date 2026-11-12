"""Onboarding router."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from api.deps import DbSession, get_current_user
from api.schemas import (
    ProfileConfirmRequest,
    ProfileConfirmResponse,
    QuestionnaireRequest,
    QuestionnaireResponse,
    ResumeUploadResponse,
    SessionUser,
)
from api.services.onboarding_service import (
    ALLOWED_RESUME_TYPES,
    MAX_RESUME_BYTES,
    onboarding_service,
)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.post("/resume", response_model=ResumeUploadResponse)
async def upload_resume(
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
    file: UploadFile = File(...),
) -> ResumeUploadResponse:
    """
    Upload resume (PDF/DOCX). Max 5MB.
    Text is extracted locally from the file; the user confirms fields on the next step.
    """
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
        return onboarding_service.handle_resume_upload(
            db,
            user.id,
            filename=filename,
            content_type=content_type,
            size=len(data),
            data=data,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/profile/confirm", response_model=ProfileConfirmResponse)
async def confirm_profile(
    body: ProfileConfirmRequest,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> ProfileConfirmResponse:
    """Confirm or edit parsed profile facts with per-fact status."""
    return onboarding_service.save_profile(
        db,
        user.id,
        body.facts,
        skill_ids=body.skill_ids,
        experiences=body.experiences,
        education=body.education,
        identity=body.identity,
    )


@router.post("/questionnaire", response_model=QuestionnaireResponse)
async def submit_questionnaire(
    body: QuestionnaireRequest,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> QuestionnaireResponse:
    """Submit onboarding questionnaire — enqueues queue backfill worker job."""
    return onboarding_service.save_questionnaire(db, user.id, body)
