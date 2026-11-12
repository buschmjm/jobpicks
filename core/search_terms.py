"""User-driven global search term registry for ingest."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from ingest.pipeline import normalize_text
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.models import SearchTerm

DAILY_TERM_FETCH_CAP = 20


def register_terms(
    session: Session,
    user_id: uuid.UUID,
    titles: list[str],
) -> list[str]:
    """Upsert target titles into search_terms; return newly added normalized terms."""
    added: list[str] = []
    seen: set[str] = set()

    for raw in titles:
        term = raw.strip()
        if not term:
            continue
        normalized = normalize_text(term)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)

        existing = session.scalar(
            select(SearchTerm).where(SearchTerm.normalized_term == normalized)
        )
        if existing is not None:
            if existing.contributed_by_user_id is None:
                existing.contributed_by_user_id = user_id
            if not existing.is_active:
                existing.is_active = True
                added.append(existing.term)
            continue

        session.add(
            SearchTerm(
                term=term,
                normalized_term=normalized,
                contributed_by_user_id=user_id,
                is_active=True,
            )
        )
        added.append(term)

    if added:
        session.flush()
    return added


def load_active_terms(session: Session) -> tuple[str, ...]:
    """All active search terms; empty when none registered yet."""
    rows = session.scalars(
        select(SearchTerm.term)
        .where(SearchTerm.is_active.is_(True))
        .order_by(SearchTerm.term)
    ).all()
    return tuple(rows)


def select_terms_for_ingest(
    session: Session,
    *,
    terms: tuple[str, ...] | None = None,
    cap: int = DAILY_TERM_FETCH_CAP,
) -> tuple[str, ...]:
    """Pick terms to fetch: explicit subset, or oldest-fetched active terms up to cap."""
    if terms:
        return terms

    rows = session.scalars(
        select(SearchTerm)
        .where(SearchTerm.is_active.is_(True))
        .order_by(SearchTerm.last_fetched_at.asc().nullsfirst(), SearchTerm.created_at.asc())
        .limit(max(1, cap))
    ).all()
    return tuple(row.term for row in rows)


def mark_terms_fetched(session: Session, terms: tuple[str, ...]) -> None:
    """Record fetch time for rotation on daily cron runs."""
    if not terms:
        return
    now = datetime.now(tz=UTC)
    normalized = {normalize_text(term) for term in terms}
    rows = session.scalars(
        select(SearchTerm).where(SearchTerm.normalized_term.in_(normalized))
    ).all()
    for row in rows:
        row.last_fetched_at = now
    session.flush()
