"""Cache embeddings for target title strings (A6)."""

from __future__ import annotations

import logging
import re

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from core.models import TitleEmbeddingCache

logger = logging.getLogger(__name__)


def normalize_title_key(title: str) -> str:
    collapsed = re.sub(r"\s+", " ", title.strip().lower())
    return collapsed


def get_title_embedding(session: Session, title: str) -> list[float] | None:
    key = normalize_title_key(title)
    if not key:
        return None
    row = session.scalar(select(TitleEmbeddingCache).where(TitleEmbeddingCache.title_key == key))
    if row is not None:
        return list(row.embedding)
    try:
        from inference.embeddings import embed_text

        vector = embed_text(title.strip())
    except Exception:
        logger.warning("title embedding failed for %r", title, exc_info=True)
        return None
    session.merge(
        TitleEmbeddingCache(
            title_key=key,
            title_display=title.strip(),
            embedding=vector,
        )
    )
    session.flush()
    return vector


def get_title_embeddings(session: Session, titles: list[str]) -> dict[str, list[float]]:
    result: dict[str, list[float]] = {}
    for title in titles:
        vector = get_title_embedding(session, title)
        if vector is not None:
            result[normalize_title_key(title)] = vector
    return result


def invalidate_title_embeddings(session: Session, titles: list[str]) -> int:
    keys = [normalize_title_key(t) for t in titles if t.strip()]
    if not keys:
        return 0
    result = session.execute(
        delete(TitleEmbeddingCache).where(TitleEmbeddingCache.title_key.in_(keys))
    )
    session.flush()
    from sqlalchemy.engine import CursorResult

    if isinstance(result, CursorResult):
        return result.rowcount or 0
    return 0
