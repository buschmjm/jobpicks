"""Persist parsed resume work history and education on profiles."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from api.resume_sections import normalize_highlights
from api.schemas import EducationIn, ExperienceIn
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from core.company_directory import get_or_create_company
from core.models import Profile, ProfileEducation, ProfileExperience


def replace_profile_experiences(
    session: Session,
    profile: Profile,
    rows: Sequence[ExperienceIn],
) -> list[ProfileExperience]:
    session.execute(delete(ProfileExperience).where(ProfileExperience.profile_id == profile.id))
    saved: list[ProfileExperience] = []
    for order, row in enumerate(rows[:12]):
        company = get_or_create_company(session, row.company_name) if row.company_name.strip() else None
        exp = ProfileExperience(
            profile_id=profile.id,
            company_id=company.id if company else None,
            company_name=row.company_name.strip()[:512],
            title=row.title.strip()[:512],
            location=row.location.strip()[:512] or None,
            start_date=row.start_date.strip()[:32] or None,
            end_date=row.end_date.strip()[:32] or None,
            is_current=row.is_current,
            highlights=normalize_highlights(list(row.highlights or [])),
            sort_order=order,
        )
        session.add(exp)
        saved.append(exp)
    session.flush()
    if saved:
        profile.headline = saved[0].title or profile.headline
        profile.target_titles = list(
            dict.fromkeys(exp.title for exp in saved if exp.title.strip())
        )[:20] or profile.target_titles
    return saved


def replace_profile_education(
    session: Session,
    profile: Profile,
    rows: Sequence[EducationIn],
) -> list[ProfileEducation]:
    session.execute(delete(ProfileEducation).where(ProfileEducation.profile_id == profile.id))
    saved: list[ProfileEducation] = []
    for order, row in enumerate(rows[:8]):
        edu = ProfileEducation(
            profile_id=profile.id,
            institution=row.institution.strip()[:512],
            degree=row.degree.strip()[:128] or None,
            field=row.field.strip()[:256] or None,
            end_date=row.end_date.strip()[:32] or None,
            sort_order=order,
        )
        session.add(edu)
        saved.append(edu)
    session.flush()
    return saved


def list_profile_experiences(session: Session, profile_id: uuid.UUID) -> list[ProfileExperience]:
    return list(
        session.scalars(
            select(ProfileExperience)
            .where(ProfileExperience.profile_id == profile_id)
            .order_by(ProfileExperience.sort_order)
        )
    )


def list_profile_education(session: Session, profile_id: uuid.UUID) -> list[ProfileEducation]:
    return list(
        session.scalars(
            select(ProfileEducation)
            .where(ProfileEducation.profile_id == profile_id)
            .order_by(ProfileEducation.sort_order)
        )
    )
