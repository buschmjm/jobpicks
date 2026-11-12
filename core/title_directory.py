"""Shared job-title directory backed by search_terms + live job corpus.

Users pick existing titles or create new ones. Search blends:
- the shared search_terms catalog
- titles already present on ingested jobs (ranked by frequency)
- a small built-in seed list of common US roles
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from ingest.pipeline import normalize_text
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.models import Job, JobStatus, Profile, SearchTerm

MAX_TITLE_LEN = 120
MAX_PROFILE_TITLES = 20

# Starter catalog so empty/homelab installs still have useful autofill.
COMMON_TITLE_SEEDS: tuple[str, ...] = (
    "Software Engineer",
    "Senior Software Engineer",
    "Staff Software Engineer",
    "Principal Software Engineer",
    "Frontend Engineer",
    "Backend Engineer",
    "Full Stack Engineer",
    "Platform Engineer",
    "Site Reliability Engineer",
    "DevOps Engineer",
    "Cloud Engineer",
    "Infrastructure Engineer",
    "Security Engineer",
    "Data Engineer",
    "Machine Learning Engineer",
    "AI Engineer",
    "Data Scientist",
    "Analytics Engineer",
    "Solutions Architect",
    "Software Architect",
    "Engineering Manager",
    "Technical Program Manager",
    "Product Manager",
    "Senior Product Manager",
    "Product Owner",
    "Project Manager",
    "Scrum Master",
    "QA Engineer",
    "Quality Assurance Analyst",
    "Test Engineer",
    "Business Analyst",
    "Systems Analyst",
    "Systems Administrator",
    "Network Engineer",
    "Database Administrator",
    "IT Support Specialist",
    "Help Desk Technician",
    "Technical Support Engineer",
    "Customer Success Manager",
    "Account Executive",
    "Account Manager",
    "Sales Development Representative",
    "Sales Engineer",
    "Solutions Engineer",
    "Technical Account Manager",
    "Marketing Manager",
    "Product Marketing Manager",
    "Growth Marketing Manager",
    "Content Strategist",
    "UX Designer",
    "UI Designer",
    "Product Designer",
    "Graphic Designer",
    "Operations Manager",
    "Office Manager",
    "Human Resources Manager",
    "Recruiter",
    "Talent Acquisition Specialist",
    "Finance Analyst",
    "Accountant",
    "Controller",
    "Registered Nurse",
    "Nurse Practitioner",
    "Physician Assistant",
    "Medical Assistant",
    "Physical Therapist",
    "Occupational Therapist",
    "Pharmacist",
    "Pharmacy Technician",
    "Teacher",
    "Special Education Teacher",
    "Instructional Designer",
    "Customer Service Representative",
    "Call Center Representative",
    "Warehouse Associate",
    "Logistics Coordinator",
    "Supply Chain Analyst",
    "Electrician",
    "Plumber",
    "HVAC Technician",
    "Maintenance Technician",
    "Truck Driver",
    "CDL Driver",
    "Paralegal",
    "Attorney",
    "Legal Assistant",
    "Executive Assistant",
    "Administrative Assistant",
    "Receptionist",
    "Barista",
    "Cook",
    "Chef",
    "Store Manager",
    "Retail Associate",
)


@dataclass(frozen=True)
class TitleRecord:
    id: uuid.UUID
    name: str
    normalized_name: str
    use_count: int = 0


def _display_name(raw: str) -> str:
    cleaned = " ".join(raw.strip().split())
    return cleaned[:MAX_TITLE_LEN]


def get_or_create_title(
    session: Session,
    raw_name: str,
    *,
    created_by_user_id: uuid.UUID | None = None,
) -> SearchTerm | None:
    display = _display_name(raw_name)
    normalized = normalize_text(display)
    if len(normalized) < 2:
        return None

    existing = session.scalar(
        select(SearchTerm).where(SearchTerm.normalized_term == normalized)
    )
    if existing is not None:
        if not existing.is_active:
            existing.is_active = True
        if existing.contributed_by_user_id is None and created_by_user_id is not None:
            existing.contributed_by_user_id = created_by_user_id
        return existing

    try:
        with session.begin_nested():
            row = SearchTerm(
                term=display,
                normalized_term=normalized,
                contributed_by_user_id=created_by_user_id,
                is_active=True,
            )
            session.add(row)
            session.flush()
            return row
    except IntegrityError:
        return session.scalar(
            select(SearchTerm).where(SearchTerm.normalized_term == normalized)
        )


def resolve_title_names(
    session: Session,
    names: Iterable[str],
    *,
    created_by_user_id: uuid.UUID | None = None,
) -> list[SearchTerm]:
    resolved: list[SearchTerm] = []
    seen: set[str] = set()
    for name in names:
        row = get_or_create_title(session, name, created_by_user_id=created_by_user_id)
        if row is None or row.normalized_term in seen:
            continue
        seen.add(row.normalized_term)
        resolved.append(row)
        if len(resolved) >= MAX_PROFILE_TITLES:
            break
    return resolved


def _profile_use_count(session: Session, term: str) -> int:
    count = session.scalar(
        select(func.count())
        .select_from(Profile)
        .where(Profile.target_titles.contains([term]))
    )
    return int(count or 0)


def to_title_record(session: Session, row: SearchTerm, *, job_count: int = 0) -> TitleRecord:
    return TitleRecord(
        id=row.id,
        name=row.term,
        normalized_name=row.normalized_term,
        use_count=_profile_use_count(session, row.term) + max(0, job_count),
    )


def ensure_seed_titles(session: Session) -> None:
    """Idempotently add common roles + popular titles from ingested jobs."""
    existing = int(session.scalar(select(func.count()).select_from(SearchTerm)) or 0)
    # Already warm enough — skip the heavier job backfill.
    if existing >= 100:
        return

    for name in COMMON_TITLE_SEEDS:
        get_or_create_title(session, name)

    popular = session.execute(
        select(
            Job.normalized_title,
            func.min(Job.title).label("title"),
            func.count().label("c"),
        )
        .where(
            Job.status == JobStatus.OPEN.value,
            Job.normalized_title.is_not(None),
            Job.normalized_title != "",
        )
        .group_by(Job.normalized_title)
        .having(func.count() >= 2)
        .order_by(func.count().desc())
        .limit(400)
    ).all()
    for row in popular:
        get_or_create_title(session, str(row.title))
    session.flush()


def _search_job_title_rows(
    session: Session,
    query: str,
    *,
    limit: int,
) -> list[tuple[str, str, int]]:
    """Return (display_title, normalized_title, job_count) from open jobs."""
    q = normalize_text(query)
    stmt = (
        select(
            func.min(Job.title).label("title"),
            Job.normalized_title,
            func.count().label("c"),
        )
        .where(
            Job.status == JobStatus.OPEN.value,
            Job.normalized_title.is_not(None),
            Job.normalized_title != "",
        )
        .group_by(Job.normalized_title)
    )
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            or_(
                Job.normalized_title.like(pattern),
                func.lower(Job.title).like(pattern),
            )
        )
    else:
        stmt = stmt.having(func.count() >= 2)
    stmt = stmt.order_by(func.count().desc(), func.min(Job.title).asc()).limit(limit)
    return [(str(r.title), str(r.normalized_title), int(r.c)) for r in session.execute(stmt).all()]


def search_titles(session: Session, query: str, *, limit: int = 20) -> list[TitleRecord]:
    ensure_seed_titles(session)
    limit = max(1, min(limit, 40))
    q = normalize_text(query)

    catalog_stmt = select(SearchTerm).where(SearchTerm.is_active.is_(True))
    if q:
        pattern = f"%{q}%"
        catalog_stmt = catalog_stmt.where(
            or_(
                SearchTerm.normalized_term.like(pattern),
                func.lower(SearchTerm.term).like(pattern),
            )
        )
    catalog_rows = list(
        session.scalars(catalog_stmt.order_by(SearchTerm.term).limit(limit * 4)).all()
    )

    job_hits = _search_job_title_rows(session, query, limit=limit * 2)
    job_count_by_norm = {norm: count for _, norm, count in job_hits}

    # Promote live job matches into the shared catalog so they get stable IDs.
    for display, _norm, _count in job_hits:
        get_or_create_title(session, display)

    # Re-read after promotion so job-only hits are included.
    if q:
        pattern = f"%{q}%"
        catalog_rows = list(
            session.scalars(
                select(SearchTerm)
                .where(
                    SearchTerm.is_active.is_(True),
                    or_(
                        SearchTerm.normalized_term.like(pattern),
                        func.lower(SearchTerm.term).like(pattern),
                    ),
                )
                .order_by(SearchTerm.term)
                .limit(limit * 4)
            ).all()
        )
    else:
        # Empty query: prefer titles that appear often in jobs / profiles.
        catalog_rows = list(
            session.scalars(
                select(SearchTerm)
                .where(SearchTerm.is_active.is_(True))
                .order_by(SearchTerm.term)
                .limit(300)
            ).all()
        )

    records = [
        to_title_record(
            session,
            row,
            job_count=job_count_by_norm.get(row.normalized_term, 0),
        )
        for row in catalog_rows
    ]

    seed_rank = {
        normalize_text(name): idx for idx, name in enumerate(COMMON_TITLE_SEEDS)
    }

    def rank_key(item: TitleRecord) -> tuple[int, int, int, str]:
        name_l = item.name.lower()
        starts = 0
        if q:
            starts = (
                0
                if item.normalized_name.startswith(q) or name_l.startswith(query.strip().lower())
                else 1
            )
        # Empty query: prefer curated seeds, then job popularity.
        seed = seed_rank.get(item.normalized_name, 10_000)
        return (starts, seed if not q else 0, -item.use_count, name_l)

    records.sort(key=rank_key)
    # De-dupe by normalized name while preserving rank order.
    seen: set[str] = set()
    out: list[TitleRecord] = []
    for item in records:
        if item.normalized_name in seen:
            continue
        seen.add(item.normalized_name)
        out.append(item)
        if len(out) >= limit:
            break
    return out


def titles_from_profile_strings(
    session: Session,
    names: Sequence[str] | None,
    *,
    created_by_user_id: uuid.UUID | None = None,
) -> list[TitleRecord]:
    rows = resolve_title_names(
        session,
        names or [],
        created_by_user_id=created_by_user_id,
    )
    return [to_title_record(session, row) for row in rows]
