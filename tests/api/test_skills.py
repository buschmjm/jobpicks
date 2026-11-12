"""Skill directory search, create, and profile attachment."""

from __future__ import annotations

from api.repositories.profile_repo import ProfileRepository
from api.schemas import FactStatus, ProfileFact
from api.services.auth_service import auth_service
from core.models import ProfileSkill, Skill
from core.skill_directory import (
    get_or_create_skill,
    normalize_skill_name,
    replace_job_skills,
    search_skills,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def test_normalize_skill_name() -> None:
    assert normalize_skill_name("  Kubernetes  ") == "kubernetes"
    assert normalize_skill_name("C++") == "c++"


def test_search_finds_seeded_alias(db_session: Session) -> None:
    hits = search_skills(db_session, "k8s")
    names = {skill.normalized_name for skill in hits}
    assert "kubernetes" in names


def test_get_or_create_reuses_existing(db_session: Session) -> None:
    first = get_or_create_skill(db_session, "Terraform")
    second = get_or_create_skill(db_session, "terraform")
    assert first is not None
    assert second is not None
    assert first.id == second.id


def test_create_custom_skill(db_session: Session) -> None:
    skill = get_or_create_skill(db_session, "Zig")
    assert skill is not None
    assert skill.normalized_name == "zig"
    hits = search_skills(db_session, "zig")
    assert any(row.id == skill.id for row in hits)


def test_profile_confirm_attaches_directory_skills(db_session: Session) -> None:
    _, user_id = auth_service.verify_and_create_session(db_session, "skills@example.com")
    kube = get_or_create_skill(db_session, "Kubernetes")
    zig = get_or_create_skill(db_session, "Zig")
    assert kube is not None
    assert zig is not None
    repo = ProfileRepository(db_session)
    profile = repo.save_confirmed_facts(
        user_id,
        [ProfileFact(key="title", value="SRE", status=FactStatus.confirmed)],
        skill_ids=[kube.id, zig.id],
    )
    db_session.commit()
    links = db_session.scalars(select(ProfileSkill).where(ProfileSkill.profile_id == profile.id)).all()
    assert {link.skill_id for link in links} == {kube.id, zig.id}
    assert profile.skills == [kube.name, zig.name]
    db_session.refresh(kube)
    assert kube.use_count >= 1


def test_job_skills_resolve_into_directory(db_session: Session) -> None:
    from core.models import Job, JobStatus, RemoteMode

    job = Job(
        company_name="Acme",
        title="SRE",
        normalized_title="sre",
        canonical_hash="skill-job-1",
        status=JobStatus.OPEN,
        remote_mode=RemoteMode.REMOTE,
    )
    db_session.add(job)
    db_session.flush()
    replace_job_skills(db_session, job.id, ["Kubernetes", "DoesNotExistYet"])
    db_session.commit()
    count = db_session.scalar(select(func.count()).select_from(Skill))
    assert count and count >= 2
    custom = db_session.scalar(select(Skill).where(Skill.normalized_name == "doesnotexistyet"))
    assert custom is not None
    assert custom.use_count >= 1
