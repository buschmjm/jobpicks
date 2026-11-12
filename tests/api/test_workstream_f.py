"""Workstream F API integration tests (FT2, FT4, FT5)."""

from __future__ import annotations

import pytest
from core.attainability import attainability
from core.job_search import JobSearchFilters, JobSearchSort, search_jobs
from core.models import Job, JobStatus
from core.queue_builder import build_backfill_deck
from core.seniority import SENIORITY_C_SUITE, SENIORITY_JUNIOR, derive_seniority_from_title
from core.types import HardConstraints, RemoteMode, ScoringConfig

from tests.test_workstream_f import _job_features, _profile, _scored


def test_ft2_ceo_reach_in_search_excluded_from_deck(db_session) -> None:
    profile = _profile(seniority_level=SENIORITY_JUNIOR, target_salary=60_000.0)
    ceo_job = _job_features(
        "ceo",
        title="Chief Executive Officer",
        level=SENIORITY_C_SUITE,
        salary_min=450_000,
        salary_max=550_000,
    )
    assert derive_seniority_from_title("Chief Executive Officer") == SENIORITY_C_SUITE
    assert attainability(profile, ceo_job, session=db_session) <= 0.0101

    scored = _scored(profile, ceo_job)
    deck = build_backfill_deck(
        [scored],
        excluded_job_ids=set(),
        constraints=HardConstraints(min_salary=60_000),
        profile=profile,
        config=ScoringConfig(),
    )
    assert all(item.job.job_id != "ceo" for item in deck)

    row = Job(
        company_name="BigCo",
        title="Chief Executive Officer",
        normalized_title="chief executive officer",
        canonical_hash="ceo-hash",
        status=JobStatus.OPEN,
        remote_mode=RemoteMode.REMOTE,
        description="Lead the company as CEO",
        seniority_int=SENIORITY_C_SUITE,
        salary_min=450_000,
        salary_max=550_000,
        country="US",
        is_direct=True,
    )
    db_session.add(row)
    db_session.commit()

    results = search_jobs(db_session, "CEO", profile, limit=20)
    assert results
    ceo_hit = next(hit for hit in results if "chief" in hit.job.title.lower())
    assert ceo_hit.reach is True


def test_ft4_search_list_differs_from_deck(db_session) -> None:
    profile = _profile()
    for idx, title in enumerate(["Alpha Engineer", "Beta Designer"]):
        db_session.add(
            Job(
                company_name="Co",
                title=title,
                normalized_title=title.lower(),
                canonical_hash=f"hash-{idx}",
                status=JobStatus.OPEN,
                remote_mode=RemoteMode.REMOTE,
                description=title,
                seniority_int=2,
                country="US",
                is_direct=True,
            )
        )
    db_session.commit()

    deck = build_backfill_deck(
        [
            _scored(profile, _job_features("a", title="Alpha Engineer", level=2)),
            _scored(profile, _job_features("b", title="Beta Designer", level=2)),
        ],
        excluded_job_ids=set(),
        constraints=HardConstraints(),
        profile=profile,
        config=ScoringConfig(min_match_score=0.1, min_explore_score=0.1),
    )
    search = search_jobs(db_session, "Beta", profile, limit=10)
    deck_ids = [item.job.job_id for item in deck]
    search_ids = [hit.job.job_id for hit in search]
    assert search_ids
    assert search_ids[0] == "b" or deck_ids != search_ids


def test_ft5_empty_profile_search(db_session) -> None:
    db_session.add(
        Job(
            company_name="Co",
            title="Staff Engineer",
            normalized_title="staff engineer",
            canonical_hash="staff-1",
            status=JobStatus.OPEN,
            remote_mode=RemoteMode.REMOTE,
            description="Build systems",
            country="US",
            is_direct=True,
        )
    )
    db_session.commit()
    results = search_jobs(db_session, "Staff", None, limit=10)
    assert results
    assert results[0].deck_rank_score == pytest.approx(0.5)


def test_search_filters_remote_mode(db_session) -> None:
    db_session.add(
        Job(
            company_name="RemoteCo",
            title="Remote Engineer",
            normalized_title="remote engineer",
            canonical_hash="remote-1",
            status=JobStatus.OPEN,
            remote_mode=RemoteMode.REMOTE,
            description="Build systems remotely",
            country="US",
            is_direct=True,
        )
    )
    db_session.add(
        Job(
            company_name="OfficeCo",
            title="Onsite Engineer",
            normalized_title="onsite engineer",
            canonical_hash="onsite-1",
            status=JobStatus.OPEN,
            remote_mode=RemoteMode.ONSITE,
            description="Build systems onsite",
            country="US",
            is_direct=True,
        )
    )
    db_session.commit()

    remote_only = search_jobs(
        db_session,
        "",
        None,
        filters=JobSearchFilters(remote_modes=frozenset({"remote"})),
        sort=JobSearchSort.DATE,
        limit=10,
    )
    assert len(remote_only) == 1
    assert remote_only[0].job.title == "Remote Engineer"
