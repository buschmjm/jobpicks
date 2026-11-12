"""Shared fixtures for API repository and service tests."""

from __future__ import annotations

import json
from collections.abc import Generator

import pytest
from core.database import Base
from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Text, TypeDecorator, Uuid, create_engine
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Session, sessionmaker

_TYPE_PATCHES: list[tuple[object, object]] = []


class _SQLiteVector(TypeDecorator):
    """Store pgvector columns as JSON text when tests run on SQLite."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: object | None, dialect: object) -> str | None:
        if value is None:
            return None
        return json.dumps(value)

    def process_result_value(self, value: object | None, dialect: object) -> list[float] | None:
        if value is None:
            return None
        if isinstance(value, list):
            return value
        return json.loads(str(value))


def _sqlite_compat_metadata() -> None:
    """Replace Postgres-only column types so tables can be created on SQLite."""
    for table in Base.metadata.tables.values():
        for column in table.columns:
            col_type = column.type
            if isinstance(col_type, Vector):
                _TYPE_PATCHES.append((column, col_type))
                column.type = _SQLiteVector()
            elif isinstance(col_type, JSONB):
                _TYPE_PATCHES.append((column, col_type))
                column.type = JSON()
            elif isinstance(col_type, UUID):
                _TYPE_PATCHES.append((column, col_type))
                column.type = Uuid(as_uuid=True)


def _restore_metadata() -> None:
    for column, original in _TYPE_PATCHES:
        column.type = original  # type: ignore[misc]
    _TYPE_PATCHES.clear()


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    _sqlite_compat_metadata()
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        _restore_metadata()
