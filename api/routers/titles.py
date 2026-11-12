"""Job title directory — search existing titles or create a new one."""

from __future__ import annotations

from core.title_directory import TitleRecord, get_or_create_title, search_titles, titles_from_profile_strings
from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.deps import DbSession, get_current_user
from api.schemas import (
    SessionUser,
    TitleCreateRequest,
    TitleOut,
    TitleResolveRequest,
    TitleSearchResponse,
)

router = APIRouter(prefix="/titles", tags=["titles"])


def _to_out(record: TitleRecord) -> TitleOut:
    return TitleOut(
        id=record.id,
        name=record.name,
        normalized_name=record.normalized_name,
        use_count=record.use_count,
    )


@router.get("", response_model=TitleSearchResponse)
def search_title_directory(
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
    q: str = Query(default="", max_length=120),
    limit: int = Query(default=20, ge=1, le=40),
) -> TitleSearchResponse:
    _ = user
    items = [_to_out(item) for item in search_titles(db, q, limit=limit)]
    # Persist seed / job-promoted titles discovered during search.
    db.commit()
    return TitleSearchResponse(items=items, query=q)


@router.post("", response_model=TitleOut)
def create_title(
    body: TitleCreateRequest,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> TitleOut:
    row = get_or_create_title(db, body.name, created_by_user_id=user.id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Title is too short",
        )
    db.commit()
    db.refresh(row)
    from core.title_directory import to_title_record

    return _to_out(to_title_record(db, row))


@router.post("/resolve", response_model=TitleSearchResponse)
def resolve_titles(
    body: TitleResolveRequest,
    db: DbSession,
    user: SessionUser = Depends(get_current_user),
) -> TitleSearchResponse:
    items = [
        _to_out(item)
        for item in titles_from_profile_strings(
            db,
            body.names,
            created_by_user_id=user.id,
        )
    ]
    db.commit()
    return TitleSearchResponse(items=items, query="")
