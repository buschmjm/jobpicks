"""Database engine, session factory, and declarative base."""

from __future__ import annotations

import os
from collections.abc import Generator
from functools import lru_cache
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DEFAULT_DATABASE_URL = "postgresql+psycopg://localhost/job_platform"


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


def get_database_url() -> str:
    env_url = os.environ.get("DATABASE_URL")
    if env_url:
        return env_url
    try:
        from api.settings import settings

        return settings.database_url
    except ImportError:
        return DEFAULT_DATABASE_URL


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_engine(get_database_url(), pool_pre_ping=True)


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(
        bind=get_engine(),
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )


class _LazyEngine:
    def __getattr__(self, name: str) -> Any:
        return getattr(get_engine(), name)


class _LazySessionLocal:
    def __call__(self, *args: Any, **kwargs: Any) -> Session:
        return get_session_factory()(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(get_session_factory(), name)


engine = _LazyEngine()
SessionLocal = _LazySessionLocal()


def get_session() -> Generator[Session, None, None]:
    """Yield a database session and ensure it is closed afterward."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
