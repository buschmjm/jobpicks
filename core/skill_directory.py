"""Shared skill directory: search existing names, create when missing.

Skills are a first-class catalog (not free-text on the profile). Resume parsing,
user typeahead, and job ingest all resolve through get-or-create so postings and
people can match on the same rows later.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence

from api.resume_skills import _EXTRA_ALIASES, SKILL_ALIASES, default_display_name
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from core.models import JobSkill, Profile, ProfileSkill, Skill, SkillAlias

MAX_SKILL_NAME_LEN = 80
MAX_PROFILE_SKILLS = 30


def normalize_skill_name(raw: str) -> str:
    return " ".join(raw.strip().lower().split())[:MAX_SKILL_NAME_LEN]


def ensure_seeded(session: Session) -> None:
    existing = session.scalar(select(func.count()).select_from(Skill))
    if existing:
        return
    for canonical, aliases in SKILL_ALIASES.items():
        skill = Skill(
            name=default_display_name(canonical),
            normalized_name=canonical,
            use_count=0,
        )
        session.add(skill)
        session.flush()
        seen = {canonical}
        session.add(SkillAlias(skill_id=skill.id, normalized_name=canonical))
        for alias in aliases:
            alias_n = normalize_skill_name(alias)
            if alias_n and alias_n not in seen:
                seen.add(alias_n)
                session.add(SkillAlias(skill_id=skill.id, normalized_name=alias_n))
    for alias, canonical in _EXTRA_ALIASES.items():
        alias_skill = session.scalar(select(Skill).where(Skill.normalized_name == canonical))
        if alias_skill is None:
            continue
        alias_n = normalize_skill_name(alias)
        already = session.scalar(
            select(SkillAlias).where(SkillAlias.normalized_name == alias_n)
        )
        if already is None and alias_n:
            session.add(SkillAlias(skill_id=alias_skill.id, normalized_name=alias_n))
    session.flush()


def _lookup(session: Session, normalized: str) -> Skill | None:
    alias = session.scalar(
        select(SkillAlias)
        .options(selectinload(SkillAlias.skill))
        .where(SkillAlias.normalized_name == normalized)
    )
    if alias is not None:
        return alias.skill
    return session.scalar(select(Skill).where(Skill.normalized_name == normalized))


def get_or_create_skill(
    session: Session,
    raw_name: str,
    *,
    created_by_user_id: uuid.UUID | None = None,
) -> Skill | None:
    ensure_seeded(session)
    normalized = normalize_skill_name(raw_name)
    if len(normalized) < 2:
        return None
    found = _lookup(session, normalized)
    if found is not None:
        return found
    display = raw_name.strip()[:MAX_SKILL_NAME_LEN] or default_display_name(normalized)
    try:
        with session.begin_nested():
            skill = Skill(
                name=display,
                normalized_name=normalized,
                created_by_user_id=created_by_user_id,
                use_count=0,
            )
            session.add(skill)
            session.flush()
            session.add(SkillAlias(skill_id=skill.id, normalized_name=normalized))
            session.flush()
            return skill
    except IntegrityError:
        return _lookup(session, normalized)


def resolve_skill_names(
    session: Session,
    names: Iterable[str],
    *,
    created_by_user_id: uuid.UUID | None = None,
) -> list[Skill]:
    resolved: list[Skill] = []
    seen: set[uuid.UUID] = set()
    for name in names:
        skill = get_or_create_skill(session, name, created_by_user_id=created_by_user_id)
        if skill is None or skill.id in seen:
            continue
        seen.add(skill.id)
        resolved.append(skill)
        if len(resolved) >= MAX_PROFILE_SKILLS:
            break
    return resolved


def search_skills(session: Session, query: str, *, limit: int = 20) -> list[Skill]:
    ensure_seeded(session)
    limit = max(1, min(limit, 40))
    q = normalize_skill_name(query)
    stmt = select(Skill)
    if q:
        pattern = f"%{q}%"
        stmt = (
            stmt.outerjoin(SkillAlias)
            .where(
                or_(
                    Skill.normalized_name.like(pattern),
                    func.lower(Skill.name).like(pattern),
                    SkillAlias.normalized_name.like(pattern),
                )
            )
            .distinct()
        )
    return list(
        session.scalars(stmt.order_by(Skill.use_count.desc(), Skill.name).limit(limit)).all()
    )


def _refresh_use_counts(session: Session, skill_ids: Iterable[uuid.UUID]) -> None:
    ids = list(dict.fromkeys(skill_ids))
    if not ids:
        return
    for skill_id in ids:
        skill = session.get(Skill, skill_id)
        if skill is None:
            continue
        n_profiles = session.scalar(
            select(func.count()).select_from(ProfileSkill).where(ProfileSkill.skill_id == skill_id)
        )
        n_jobs = session.scalar(
            select(func.count()).select_from(JobSkill).where(JobSkill.skill_id == skill_id)
        )
        skill.use_count = int(n_profiles or 0) + int(n_jobs or 0)


def replace_profile_skills(session: Session, profile: Profile, skills: Sequence[Skill]) -> list[Skill]:
    previous = list(
        session.scalars(select(ProfileSkill.skill_id).where(ProfileSkill.profile_id == profile.id))
    )
    session.execute(delete(ProfileSkill).where(ProfileSkill.profile_id == profile.id))
    kept: list[Skill] = []
    seen: set[uuid.UUID] = set()
    for skill in skills[:MAX_PROFILE_SKILLS]:
        if skill.id in seen:
            continue
        seen.add(skill.id)
        session.add(ProfileSkill(profile_id=profile.id, skill_id=skill.id))
        kept.append(skill)
    session.flush()
    profile.skills = [skill.name for skill in kept]
    _refresh_use_counts(session, [*previous, *[s.id for s in kept]])
    return kept


def replace_job_skills(session: Session, job_id: uuid.UUID, names: Iterable[str] | None) -> None:
    previous = list(session.scalars(select(JobSkill.skill_id).where(JobSkill.job_id == job_id)))
    session.execute(delete(JobSkill).where(JobSkill.job_id == job_id))
    kept: list[uuid.UUID] = []
    if names:
        for skill in resolve_skill_names(session, names):
            session.add(JobSkill(job_id=job_id, skill_id=skill.id))
            kept.append(skill.id)
    session.flush()
    _refresh_use_counts(session, [*previous, *kept])
