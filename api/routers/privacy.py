"""Privacy router — delete-my-data (plan §12, E2.13)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from api.deps import DbSession, get_current_user
from api.schemas import DeleteMyDataResponse, ExportMyDataResponse, SessionUser
from api.services.privacy_service import delete_user_data, export_user_data

router = APIRouter(prefix="/privacy", tags=["privacy"])


@router.get("/export", response_model=ExportMyDataResponse)
async def export_my_data(
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> ExportMyDataResponse:
    """GDPR access/portability export (JSON)."""
    payload = export_user_data(db, user.id)
    return ExportMyDataResponse(
        exported_at=str(payload["exported_at"]),
        user_id=str(payload["user_id"]),
        email=str(payload["email"]),
        data=payload,
    )


@router.delete("/delete-my-data", response_model=DeleteMyDataResponse, status_code=status.HTTP_200_OK)
async def delete_my_data(
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> DeleteMyDataResponse:
    """
    CCPA-style deletion: hard-delete profile/resume, delete todo/queue rows,
    anonymize analytics events (aggregates preserved).
    """
    counts = delete_user_data(db, user.id)
    db.commit()
    return DeleteMyDataResponse(deleted=True, counts=counts)
