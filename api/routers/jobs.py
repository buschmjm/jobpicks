from __future__ import annotations

import uuid

from core.apply.job_from_url import JobFromUrlError
from fastapi import APIRouter, Depends, HTTPException

from api.deps import DbSession, get_current_user
from api.schemas import JobDescriptionResponse, JobFromUrlRequest, JobFromUrlResponse, SessionUser
from api.services.job_description_service import get_job_description
from api.services.job_import_service import job_import_service

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}/description", response_model=JobDescriptionResponse)
def read_job_description(
    job_id: uuid.UUID,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> JobDescriptionResponse:
    try:
        description, truncated, top_pct, p_top_pct = get_job_description(db, job_id, user_id=user.id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return JobDescriptionResponse(
        description=description,
        truncated=truncated,
        competitiveness_top_percent=top_pct,
        competitiveness_p_top_percent=p_top_pct,
    )


@router.post("/from-url", response_model=JobFromUrlResponse)
def import_job_from_url(
    body: JobFromUrlRequest,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> JobFromUrlResponse:
    """Add a job by ATS apply URL, create a todo item, and optionally prefetch packet."""
    try:
        return job_import_service.import_from_url(db, user.id, body)
    except JobFromUrlError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
