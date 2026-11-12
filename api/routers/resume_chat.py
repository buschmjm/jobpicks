"""Resume builder chat endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from api.deps import DbSession, get_current_user
from api.schemas import (
    ResumeBuilderMessageCreate,
    ResumeBuilderThreadResponse,
    ResumeProposalApplyResponse,
    ResumeProposalListResponse,
    ResumeProposalResponse,
    SessionUser,
)
from api.services.resume_builder_chat_service import (
    clear_thread,
    get_thread,
    iter_builder_sse,
    prepare_stream,
)
from api.services.resume_proposal_service import apply, list_proposals, reject

router = APIRouter(prefix="/resume", tags=["resume-chat"])


@router.get("/chat/messages", response_model=ResumeBuilderThreadResponse)
def list_messages(
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
    variant_id: UUID | None = Query(default=None),
) -> ResumeBuilderThreadResponse:
    try:
        return get_thread(db, user.id, variant_id=variant_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/chat/messages", response_model=ResumeBuilderThreadResponse)
def delete_messages(
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
    variant_id: UUID | None = Query(default=None),
) -> ResumeBuilderThreadResponse:
    try:
        return clear_thread(db, user.id, variant_id=variant_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/chat/stream")
def post_chat_stream(
    body: ResumeBuilderMessageCreate,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> StreamingResponse:
    try:
        prep = prepare_stream(db, user.id, body)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return StreamingResponse(
        iter_builder_sse(prep),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/chat/proposals", response_model=ResumeProposalListResponse)
def get_proposals(
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
    variant_id: UUID | None = Query(default=None),
) -> ResumeProposalListResponse:
    return list_proposals(db, user.id, variant_id=variant_id)


@router.post("/chat/proposals/{proposal_id}/apply", response_model=ResumeProposalApplyResponse)
def post_apply_proposal(
    proposal_id: UUID,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> ResumeProposalApplyResponse:
    try:
        return apply(db, user.id, proposal_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/chat/proposals/{proposal_id}/reject", response_model=ResumeProposalResponse)
def post_reject_proposal(
    proposal_id: UUID,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> ResumeProposalResponse:
    try:
        return reject(db, user.id, proposal_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
