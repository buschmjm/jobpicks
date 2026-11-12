"""Career assistant endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from api.deps import DbSession, get_current_user
from api.schemas import (
    CareerMessage,
    CareerMessageCreate,
    CareerThreadResponse,
    SessionUser,
    TitleSuggestionsResponse,
)
from api.services.career_advisor_service import (
    clear_thread,
    get_thread,
    iter_advisor_sse,
    prepare_stream,
    request_cancel,
    send_message,
)
from api.services.career_service import get_title_suggestions

router = APIRouter(prefix="/career", tags=["career"])


@router.get("/title-suggestions", response_model=TitleSuggestionsResponse)
def title_suggestions(
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
    goals: str | None = Query(default=None, max_length=2000),
) -> TitleSuggestionsResponse:
    # Sync def so FastAPI runs this in a threadpool; blocking Ollama calls must
    # not stall the event loop (otherwise /health probes kill the API mid-chat).
    return get_title_suggestions(db, user.id, goals=goals)


@router.get("/messages", response_model=CareerThreadResponse)
def list_messages(
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> CareerThreadResponse:
    return get_thread(db, user.id)


@router.delete("/messages", response_model=CareerThreadResponse)
def delete_messages(
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> CareerThreadResponse:
    return clear_thread(db, user.id)


@router.post("/messages", response_model=CareerThreadResponse)
def post_message(
    body: CareerMessageCreate,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> CareerThreadResponse:
    return send_message(db, user.id, body)


@router.post("/messages/stream")
def post_message_stream(
    body: CareerMessageCreate,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> StreamingResponse:
    prep = prepare_stream(db, user.id, body)
    return StreamingResponse(
        iter_advisor_sse(prep),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/messages/{message_id}/cancel", response_model=CareerMessage)
def cancel_message_stream(
    message_id: UUID,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> CareerMessage:
    return request_cancel(db, user.id, message_id)
