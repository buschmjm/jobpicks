"""Tests for target title embedding cache (A6)."""

from __future__ import annotations

from unittest.mock import patch

from core.models import TitleEmbeddingCache
from core.title_embedding_cache import (
    get_title_embedding,
    invalidate_title_embeddings,
    normalize_title_key,
)
from sqlalchemy import select
from sqlalchemy.orm import Session


def test_title_embedding_cache_round_trip(db_session: Session) -> None:
    vector = [0.1, 0.2, 0.3]
    with patch("inference.embeddings.embed_text", return_value=vector):
        first = get_title_embedding(db_session, "Platform Engineer")
        second = get_title_embedding(db_session, "platform engineer")

    assert first == vector
    assert second == vector
    row = db_session.scalar(
        select(TitleEmbeddingCache).where(
            TitleEmbeddingCache.title_key == normalize_title_key("Platform Engineer")
        )
    )
    assert row is not None


def test_title_embedding_cache_invalidates_on_edit(db_session: Session) -> None:
    vector = [0.4, 0.5, 0.6]
    with patch("inference.embeddings.embed_text", return_value=vector):
        get_title_embedding(db_session, "SRE")

    removed = invalidate_title_embeddings(db_session, ["SRE"])
    assert removed == 1
    row = db_session.scalar(
        select(TitleEmbeddingCache).where(TitleEmbeddingCache.title_key == normalize_title_key("SRE"))
    )
    assert row is None
