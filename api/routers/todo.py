"""Apply To-Do list router."""

from uuid import UUID

from core.packet_entitlements import PacketLimitExceeded
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from api.deps import DbSession, get_current_user
from api.schemas import (
    ApplicationPacketAssistRequest,
    ApplicationPacketOpenResponse,
    ApplicationPacketPatchRequest,
    ApplicationPacketResponse,
    ApplicationPacketReuseRequest,
    ApplicationStepTemplateResponse,
    ApplicationStepTemplateUpdateRequest,
    PreparedPacketListResponse,
    SessionUser,
    TodoApplyClickResponse,
    TodoCreateRequest,
    TodoItem,
    TodoListResponse,
    TodoSelfReportRequest,
    TodoStatus,
    TodoStepsUpdateRequest,
    TodoUpdateRequest,
)
from api.services.application_packet_service import application_packet_service
from api.services.todo_service import todo_service

router = APIRouter(prefix="/todo", tags=["todo"])


@router.get("", response_model=TodoListResponse)
async def list_todos(
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
    status_filter: TodoStatus | None = Query(default=None, alias="status"),
) -> TodoListResponse:
    items = todo_service.list_items(db, user.id, status_filter)
    return TodoListResponse(items=items, total=len(items))


@router.get("/prepared", response_model=PreparedPacketListResponse)
async def list_prepared_packets(
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> PreparedPacketListResponse:
    return application_packet_service.list_prepared(db, user.id)


@router.get("/packets/{packet_id}", response_model=ApplicationPacketResponse)
async def get_packet_by_id(
    packet_id: UUID,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> ApplicationPacketResponse:
    packet = application_packet_service.get_by_id(db, user.id, packet_id)
    if not packet:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    return packet


@router.patch("/packets/{packet_id}", response_model=ApplicationPacketResponse)
async def patch_packet_by_id(
    packet_id: UUID,
    body: ApplicationPacketPatchRequest,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> ApplicationPacketResponse:
    packet = application_packet_service.patch_by_id(db, user.id, packet_id, body)
    if not packet:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    return packet


@router.post("", response_model=TodoItem, status_code=status.HTTP_201_CREATED)
async def create_todo(
    body: TodoCreateRequest,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> TodoItem:
    try:
        return todo_service.create(db, user.id, body.job_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/steps/template", response_model=ApplicationStepTemplateResponse)
async def get_step_template(
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> ApplicationStepTemplateResponse:
    steps = todo_service.get_step_template(db, user.id)
    return ApplicationStepTemplateResponse(steps=steps)


@router.put("/steps/template", response_model=ApplicationStepTemplateResponse)
async def save_step_template(
    body: ApplicationStepTemplateUpdateRequest,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> ApplicationStepTemplateResponse:
    steps = todo_service.save_step_template(db, user.id, body.steps)
    return ApplicationStepTemplateResponse(steps=steps)


@router.get("/{item_id}", response_model=TodoItem)
async def get_todo(
    item_id: UUID,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> TodoItem:
    item = todo_service.get_item(db, user.id, item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Todo item not found")
    return item


@router.patch("/{item_id}", response_model=TodoItem)
async def update_todo(
    item_id: UUID,
    body: TodoUpdateRequest,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> TodoItem:
    if body.status is None and body.application_steps is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide status and/or application_steps",
        )
    item = todo_service.update_item(
        db,
        user.id,
        item_id,
        status=body.status,
        application_steps=body.application_steps,
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Todo item not found")
    return item


@router.put("/{item_id}/steps", response_model=TodoItem)
async def update_todo_steps(
    item_id: UUID,
    body: TodoStepsUpdateRequest,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> TodoItem:
    item = todo_service.update_steps(db, user.id, item_id, body.steps)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Todo item not found")
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_todo(
    item_id: UUID,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> None:
    if not todo_service.delete(db, user.id, item_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Todo item not found")


@router.post("/{item_id}/apply-click", response_model=TodoApplyClickResponse)
async def apply_click(
    item_id: UUID,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> TodoApplyClickResponse:
    """Track apply link click — client opens source_url in new tab."""
    item = todo_service.record_apply_click(db, user.id, item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Todo item not found")
    return TodoApplyClickResponse(source_url=item.source_url, todo_item_id=item.id)


@router.post("/{item_id}/self-report", response_model=TodoItem)
async def self_report_apply(
    item_id: UUID,
    body: TodoSelfReportRequest,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> TodoItem:
    """Did you apply? self-report after clicking through."""
    item = todo_service.record_self_report(db, user.id, item_id, body.did_apply)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Todo item not found")
    return item


@router.post("/{item_id}/packet", response_model=ApplicationPacketResponse)
async def generate_packet(
    item_id: UUID,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> ApplicationPacketResponse:
    try:
        return application_packet_service.request_generate(db, user.id, item_id)
    except PacketLimitExceeded as exc:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/{item_id}/packet", response_model=ApplicationPacketResponse)
async def get_packet(
    item_id: UUID,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> ApplicationPacketResponse:
    packet = application_packet_service.get(db, user.id, item_id)
    if not packet:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application packet not found")
    return packet


@router.patch("/{item_id}/packet", response_model=ApplicationPacketResponse)
async def patch_packet(
    item_id: UUID,
    body: ApplicationPacketPatchRequest,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> ApplicationPacketResponse:
    packet = application_packet_service.patch(db, user.id, item_id, body)
    if not packet:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application packet not found")
    return packet


@router.post("/{item_id}/packet/reuse", response_model=ApplicationPacketResponse)
async def reuse_packet(
    item_id: UUID,
    body: ApplicationPacketReuseRequest,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> ApplicationPacketResponse:
    try:
        return application_packet_service.reuse_from(db, user.id, item_id, body.source_packet_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/{item_id}/packet/open", response_model=ApplicationPacketOpenResponse)
def open_packet(
    item_id: UUID,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> ApplicationPacketOpenResponse:
    try:
        return application_packet_service.open(db, user.id, item_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/{item_id}/packet/assist/stream")
def packet_assist_stream(
    item_id: UUID,
    body: ApplicationPacketAssistRequest,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> StreamingResponse:
    return StreamingResponse(
        application_packet_service.iter_assist_sse(
            db,
            user.id,
            item_id,
            question=body.question,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
