"""Resume variant persistence for conversational builder."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from core.models import ResumeVariant
from sqlalchemy import select, update
from sqlalchemy.orm import Session


class ResumeVariantRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_variants(self, user_id: uuid.UUID) -> list[ResumeVariant]:
        return list(
            self._session.scalars(
                select(ResumeVariant)
                .where(ResumeVariant.user_id == user_id)
                .order_by(ResumeVariant.created_at.asc())
            )
        )

    def get_variant(self, user_id: uuid.UUID, variant_id: uuid.UUID) -> ResumeVariant | None:
        return self._session.scalar(
            select(ResumeVariant)
            .where(ResumeVariant.id == variant_id)
            .where(ResumeVariant.user_id == user_id)
        )

    def get_by_slug(self, user_id: uuid.UUID, slug: str) -> ResumeVariant | None:
        return self._session.scalar(
            select(ResumeVariant)
            .where(ResumeVariant.user_id == user_id)
            .where(ResumeVariant.slug == slug)
        )

    def create(
        self,
        user_id: uuid.UUID,
        *,
        slug: str,
        label: str,
        headline: str | None = None,
        summary_override: str | None = None,
        target_titles: list[str] | None = None,
        emphasis_notes: str | None = None,
        is_default: bool = False,
    ) -> ResumeVariant:
        if is_default:
            self._clear_default(user_id)
        row = ResumeVariant(
            user_id=user_id,
            slug=slug.strip(),
            label=label.strip(),
            headline=headline,
            summary_override=summary_override,
            target_titles=list(target_titles or []),
            emphasis_notes=emphasis_notes,
            is_default=is_default,
        )
        self._session.add(row)
        self._session.flush()
        return row

    def update(
        self,
        variant: ResumeVariant,
        *,
        label: str | None = None,
        headline: str | None = None,
        summary_override: str | None = None,
        target_titles: list[str] | None = None,
        emphasis_notes: str | None = None,
        is_default: bool | None = None,
    ) -> ResumeVariant:
        if label is not None:
            variant.label = label.strip()
        if headline is not None:
            variant.headline = headline
        if summary_override is not None:
            variant.summary_override = summary_override
        if target_titles is not None:
            variant.target_titles = list(target_titles)
        if emphasis_notes is not None:
            variant.emphasis_notes = emphasis_notes
        if is_default is not None:
            if is_default:
                self._clear_default(variant.user_id)
            variant.is_default = is_default
        variant.updated_at = datetime.now(UTC)
        self._session.flush()
        return variant

    def delete(self, user_id: uuid.UUID, variant_id: uuid.UUID) -> bool:
        row = self.get_variant(user_id, variant_id)
        if row is None:
            return False
        self._session.delete(row)
        self._session.flush()
        return True

    def _clear_default(self, user_id: uuid.UUID) -> None:
        self._session.execute(
            update(ResumeVariant)
            .where(ResumeVariant.user_id == user_id)
            .where(ResumeVariant.is_default.is_(True))
            .values(is_default=False, updated_at=datetime.now(UTC))
        )
