"""Deck / swipe queue router."""

from fastapi import APIRouter, Depends, HTTPException, status

from api.deps import DbSession, get_current_user
from api.schemas import (
    ChangeDecisionRequest,
    ChangeDecisionResponse,
    DeckNextResponse,
    DeckStatusResponse,
    DwellRequest,
    DwellResponse,
    SessionUser,
    SwipeRequest,
    SwipeResponse,
)
from api.services.deck_service import deck_service

router = APIRouter(prefix="/deck", tags=["deck"])


@router.get("/status", response_model=DeckStatusResponse)
async def get_deck_status(
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> DeckStatusResponse:
    """Poll while the deck is being built after onboarding or ingest."""
    return deck_service.get_status(db, user.id)


@router.get("/next", response_model=DeckNextResponse)
async def get_next_card(
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> DeckNextResponse:
    """Get the next card in the user's swipe queue."""
    return deck_service.get_next(db, user.id)


@router.post("/swipe", response_model=SwipeResponse)
async def swipe_card(
    body: SwipeRequest,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> SwipeResponse:
    """
    Record swipe action: right (interested), left (not interested), skip (defer).
    Left swipe accepts optional reason chip for preference learning.
    """
    result = deck_service.swipe(
        db,
        user.id,
        body.queue_item_id,
        body.action,
        body.reason,
        body.dwell_ms,
    )
    if not result.success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result.message)
    return result


@router.post("/change-decision", response_model=ChangeDecisionResponse)
async def change_decision(
    body: ChangeDecisionRequest,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> ChangeDecisionResponse:
    """Update a past swipe decision (interested / pass / skip)."""
    result = deck_service.change_decision(
        db,
        user.id,
        body.queue_item_id,
        body.action,
        body.reason,
    )
    if not result.success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result.message)
    return result


@router.post("/dwell", response_model=DwellResponse)
async def record_dwell(
    body: DwellRequest,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> DwellResponse:
    """Record card view dwell time for mindless-swipe guard (§10)."""
    return deck_service.record_dwell(db, user.id, body.queue_item_id, body.dwell_ms)
