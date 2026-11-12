"""Tests for user-driven search term registration."""

from __future__ import annotations

import uuid

from core.models import SearchTerm
from core.search_terms import load_active_terms, register_terms
from sqlalchemy import select
from sqlalchemy.orm import Session


def test_register_terms_adds_new(db_session: Session) -> None:
    user_id = uuid.uuid4()
    added = register_terms(db_session, user_id, ["Registered Nurse", "Charge Nurse"])
    db_session.commit()

    assert set(added) == {"Registered Nurse", "Charge Nurse"}
    rows = db_session.scalars(select(SearchTerm).where(SearchTerm.is_active.is_(True))).all()
    assert len(rows) == 2
    assert all(row.contributed_by_user_id == user_id for row in rows)


def test_register_terms_dedupes(db_session: Session) -> None:
    user_id = uuid.uuid4()
    first = register_terms(db_session, user_id, ["Product Manager"])
    second = register_terms(db_session, user_id, ["product manager", "Program Manager"])
    db_session.commit()

    assert first == ["Product Manager"]
    assert second == ["Program Manager"]
    assert load_active_terms(db_session) == ("Product Manager", "Program Manager")


def test_register_terms_reactivates_inactive(db_session: Session) -> None:
    user_id = uuid.uuid4()
    row = SearchTerm(
        term="Teacher",
        normalized_term="teacher",
        is_active=False,
    )
    db_session.add(row)
    db_session.commit()

    added = register_terms(db_session, user_id, ["Teacher"])
    db_session.commit()

    assert added == ["Teacher"]
    refreshed = db_session.scalar(select(SearchTerm).where(SearchTerm.normalized_term == "teacher"))
    assert refreshed is not None
    assert refreshed.is_active is True
    assert refreshed.contributed_by_user_id == user_id


def test_load_active_terms_empty(db_session: Session) -> None:
    assert load_active_terms(db_session) == ()
