"""Track external geocoding/routing API usage against free-tier caps."""

from __future__ import annotations

from datetime import UTC, datetime

from api.settings import settings
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.models import GeoApiUsage


def _month_key(when: datetime | None = None) -> str:
    now = when or datetime.now(tz=UTC)
    return now.strftime("%Y-%m")


def _daily_key(when: datetime | None = None) -> str:
    now = when or datetime.now(tz=UTC)
    return now.strftime("%Y-%m-%d")


def _get_or_create(session: Session, month: str) -> GeoApiUsage:
    row = session.scalar(select(GeoApiUsage).where(GeoApiUsage.month == month))
    if row is None:
        row = GeoApiUsage(month=month)
        session.add(row)
        session.flush()
    return row


def can_spend_geocode(session: Session, *, count: int = 1) -> bool:
    row = _get_or_create(session, _month_key())
    daily = row.geocode_calls_today or 0
    if row.geocode_day != _daily_key():
        daily = 0
    if daily + count > settings.geo_geocode_daily_cap:
        return False
    monthly_cap = int(settings.geo_geocode_monthly_cap * 0.8)
    return (row.geocode_calls or 0) + count <= monthly_cap


def record_geocode_call(session: Session, *, count: int = 1) -> None:
    row = _get_or_create(session, _month_key())
    today = _daily_key()
    if row.geocode_day != today:
        row.geocode_day = today
        row.geocode_calls_today = 0
    row.geocode_calls = (row.geocode_calls or 0) + count
    row.geocode_calls_today = (row.geocode_calls_today or 0) + count


def can_spend_matrix(session: Session, *, elements: int) -> bool:
    row = _get_or_create(session, _month_key())
    monthly_cap = int(settings.geo_matrix_monthly_cap * 0.8)
    return (row.matrix_elements or 0) + elements <= monthly_cap


def record_matrix_elements(session: Session, *, elements: int) -> None:
    row = _get_or_create(session, _month_key())
    row.matrix_elements = (row.matrix_elements or 0) + elements
