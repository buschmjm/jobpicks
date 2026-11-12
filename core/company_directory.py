"""Get-or-create company rows for resume experience linking."""

from __future__ import annotations

from ingest.pipeline import normalize_text
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.models import Company


def get_or_create_company(session: Session, raw_name: str) -> Company | None:
    name = raw_name.strip()[:512]
    normalized = normalize_text(name)
    if len(normalized) < 2:
        return None
    found = session.scalar(select(Company).where(Company.normalized_name == normalized))
    if found is not None:
        return found
    try:
        with session.begin_nested():
            company = Company(name=name, normalized_name=normalized)
            session.add(company)
            session.flush()
            return company
    except IntegrityError:
        return session.scalar(select(Company).where(Company.normalized_name == normalized))
