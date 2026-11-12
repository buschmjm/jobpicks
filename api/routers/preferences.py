"""Location and commute preferences."""

from fastapi import APIRouter, Depends

from api.deps import DbSession, get_current_user
from api.schemas import PreferencesResponse, PreferencesUpdateRequest, PreferencesUpdateResponse, SessionUser
from api.services.preferences_service import preferences_service

router = APIRouter(prefix="/preferences", tags=["preferences"])


@router.get("", response_model=PreferencesResponse)
async def get_preferences(
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> PreferencesResponse:
    return preferences_service.get(db, user.id)


@router.patch("", response_model=PreferencesUpdateResponse)
async def update_preferences(
    body: PreferencesUpdateRequest,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> PreferencesUpdateResponse:
    return preferences_service.update(db, user.id, body)
