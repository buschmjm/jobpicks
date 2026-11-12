"""Saved application answers vault API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from api.deps import DbSession, get_current_user
from api.schemas import (
    SavedApplicationAnswerListResponse,
    SavedApplicationAnswerResponse,
    SavedApplicationAnswerUpsertRequest,
    SessionUser,
)
from api.services.saved_application_answer_service import saved_application_answer_service

router = APIRouter(prefix="/application-answers", tags=["application-answers"])


@router.get("", response_model=SavedApplicationAnswerListResponse)
def list_application_answers(
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> SavedApplicationAnswerListResponse:
    return saved_application_answer_service.list_answers(db, user.id)


@router.put("/{question_key}", response_model=SavedApplicationAnswerResponse)
def upsert_application_answer(
    question_key: str,
    body: SavedApplicationAnswerUpsertRequest,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> SavedApplicationAnswerResponse:
    try:
        return saved_application_answer_service.upsert(db, user.id, question_key, body)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/{question_key}", status_code=status.HTTP_204_NO_CONTENT)
def delete_application_answer(
    question_key: str,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> None:
    if not saved_application_answer_service.delete(db, user.id, question_key):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved answer not found")
