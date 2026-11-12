"""Resume variant endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from api.deps import DbSession, get_current_user
from api.schemas import (
    ResumeVariantCreate,
    ResumeVariantListResponse,
    ResumeVariantResponse,
    ResumeVariantUpdate,
    SessionUser,
)
from api.services.resume_variant_service import (
    create_variant,
    list_variants,
    set_default_variant,
    update_variant,
)

router = APIRouter(prefix="/resume", tags=["resume-variants"])


@router.get("/variants", response_model=ResumeVariantListResponse)
def get_variants(
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> ResumeVariantListResponse:
    return list_variants(db, user.id)


@router.post("/variants", response_model=ResumeVariantResponse, status_code=status.HTTP_201_CREATED)
def post_variant(
    body: ResumeVariantCreate,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> ResumeVariantResponse:
    return create_variant(db, user.id, body)


@router.patch("/variants/{variant_id}", response_model=ResumeVariantResponse)
def patch_variant(
    variant_id: UUID,
    body: ResumeVariantUpdate,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> ResumeVariantResponse:
    try:
        return update_variant(db, user.id, variant_id, body)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/variants/{variant_id}/set-default", response_model=ResumeVariantResponse)
def post_set_default_variant(
    variant_id: UUID,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> ResumeVariantResponse:
    try:
        return set_default_variant(db, user.id, variant_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
