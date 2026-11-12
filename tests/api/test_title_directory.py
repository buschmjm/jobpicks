"""Tests for shared job-title directory."""

from __future__ import annotations

from core.title_directory import get_or_create_title, search_titles
from sqlalchemy.orm import Session


def test_get_or_create_title_dedupes_normalized(db_session: Session) -> None:
    first = get_or_create_title(db_session, "Platform Engineer")
    second = get_or_create_title(db_session, " platform engineer ")
    assert first is not None
    assert second is not None
    assert first.id == second.id
    db_session.commit()


def test_search_titles_matches_substring(db_session: Session) -> None:
    get_or_create_title(db_session, "Site Reliability Engineer")
    get_or_create_title(db_session, "Registered Nurse")
    db_session.commit()

    hits = search_titles(db_session, "reliab")
    names = [hit.name for hit in hits]
    assert "Site Reliability Engineer" in names
    assert "Registered Nurse" not in names


def test_search_titles_empty_query_returns_seeded_roles(db_session: Session) -> None:
    hits = search_titles(db_session, "", limit=30)
    names = {hit.name for hit in hits}
    assert "Software Engineer" in names or "Registered Nurse" in names
