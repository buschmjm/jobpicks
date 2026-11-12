"""Resume variant service."""

from __future__ import annotations

import uuid
from typing import Any

from core.models import ResumeVariant
from sqlalchemy.orm import Session

from api.repositories.resume_variant_repo import ResumeVariantRepository
from api.schemas import (
    ResumeVariantCreate,
    ResumeVariantListResponse,
    ResumeVariantResponse,
    ResumeVariantUpdate,
)


def _variant_schema(row: ResumeVariant) -> ResumeVariantResponse:
    return ResumeVariantResponse(
        id=row.id,
        slug=row.slug,
        label=row.label,
        headline=row.headline,
        summary_override=row.summary_override,
        target_titles=list(row.target_titles or []),
        emphasis_notes=row.emphasis_notes,
        is_default=bool(row.is_default),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def list_variants(session: Session, user_id: uuid.UUID) -> ResumeVariantListResponse:
    rows = ResumeVariantRepository(session).list_variants(user_id)
    return ResumeVariantListResponse(variants=[_variant_schema(row) for row in rows])


def create_variant(
    session: Session,
    user_id: uuid.UUID,
    body: ResumeVariantCreate,
) -> ResumeVariantResponse:
    repo = ResumeVariantRepository(session)
    row = repo.create(
        user_id,
        slug=body.slug,
        label=body.label,
        headline=body.headline,
        summary_override=body.summary_override,
        target_titles=body.target_titles,
        emphasis_notes=body.emphasis_notes,
        is_default=body.is_default,
    )
    session.commit()
    session.refresh(row)
    return _variant_schema(row)


def update_variant(
    session: Session,
    user_id: uuid.UUID,
    variant_id: uuid.UUID,
    body: ResumeVariantUpdate,
) -> ResumeVariantResponse:
    repo = ResumeVariantRepository(session)
    row = repo.get_variant(user_id, variant_id)
    if row is None:
        raise LookupError("Variant not found")
    repo.update(
        row,
        label=body.label,
        headline=body.headline,
        summary_override=body.summary_override,
        target_titles=body.target_titles,
        emphasis_notes=body.emphasis_notes,
        is_default=body.is_default,
    )
    session.commit()
    session.refresh(row)
    return _variant_schema(row)


def set_default_variant(
    session: Session,
    user_id: uuid.UUID,
    variant_id: uuid.UUID,
) -> ResumeVariantResponse:
    repo = ResumeVariantRepository(session)
    row = repo.get_variant(user_id, variant_id)
    if row is None:
        raise LookupError("Variant not found")
    repo.update(row, is_default=True)
    session.commit()
    session.refresh(row)
    return _variant_schema(row)


def get_or_create_default_variant(session: Session, user_id: uuid.UUID) -> ResumeVariant:
    repo = ResumeVariantRepository(session)
    for row in repo.list_variants(user_id):
        if row.is_default:
            return row
    existing = repo.get_by_slug(user_id, "default")
    if existing is not None:
        if not existing.is_default:
            repo.update(existing, is_default=True)
        return existing
    row = repo.create(
        user_id,
        slug="default",
        label="Default",
        is_default=True,
    )
    session.flush()
    return row


def variant_context(row: ResumeVariant) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "slug": row.slug,
        "label": row.label,
        "headline": row.headline or "",
        "summary_override": row.summary_override or "",
        "target_titles": list(row.target_titles or []),
        "emphasis_notes": row.emphasis_notes or "",
    }
