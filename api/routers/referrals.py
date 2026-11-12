"""Referral program API (Workstream C2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from api.deps import DbSession, get_current_user
from api.schemas import ReferralApplyRequest, ReferralStatusResponse, SessionUser
from api.services.revenue_service import referral_service

router = APIRouter(prefix="/referrals", tags=["referrals"])


@router.get("/status", response_model=ReferralStatusResponse)
def referral_status(
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> ReferralStatusResponse:
    try:
        data = referral_service.status(db, user.id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    db.commit()
    return ReferralStatusResponse.model_validate(data)


@router.post("/apply", response_model=ReferralStatusResponse)
def apply_referral_code(
    body: ReferralApplyRequest,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> ReferralStatusResponse:
    try:
        referral_service.apply_code(db, user.id, body.code)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    data = referral_service.status(db, user.id)
    return ReferralStatusResponse.model_validate(data)
