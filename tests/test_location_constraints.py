"""Tests for remote openness and commute hard constraints."""

from __future__ import annotations

from dataclasses import replace

from core.constraints import passes_hard_constraints
from core.types import HardConstraints, JobFeatures, RemoteMode, RemoteOpenness


def _constraints(**kwargs: object) -> HardConstraints:
    base = HardConstraints(
        home_lat=30.27,
        home_lon=-97.74,
        max_commute_minutes=45,
        remote_openness=RemoteOpenness.OPEN_TO_REMOTE,
    )
    return replace(base, **kwargs)


def _job(**kwargs: object) -> JobFeatures:
    base = JobFeatures(
        job_id="j1",
        title="Engineer",
        company_id="c1",
        company_name="Acme",
        remote_mode=RemoteMode.ONSITE,
        country="US",
        location_text="Austin, TX",
        lat=30.27,
        lon=-97.74,
        commute_minutes=30,
    )
    return replace(base, **kwargs)


def test_remote_only_accepts_remote_job() -> None:
    constraints = _constraints(remote_openness=RemoteOpenness.REMOTE_ONLY)
    job = _job(remote_mode=RemoteMode.REMOTE, commute_minutes=None)
    assert passes_hard_constraints(job, constraints)


def test_remote_only_rejects_onsite_job() -> None:
    constraints = _constraints(remote_openness=RemoteOpenness.REMOTE_ONLY)
    assert not passes_hard_constraints(_job(), constraints)


def test_local_only_rejects_remote_job() -> None:
    constraints = _constraints(remote_openness=RemoteOpenness.LOCAL_ONLY)
    job = _job(remote_mode=RemoteMode.REMOTE, commute_minutes=None)
    assert not passes_hard_constraints(job, constraints)


def test_open_to_remote_accepts_both() -> None:
    constraints = _constraints(remote_openness=RemoteOpenness.OPEN_TO_REMOTE)
    assert passes_hard_constraints(_job(), constraints)
    assert passes_hard_constraints(_job(remote_mode=RemoteMode.REMOTE, commute_minutes=None), constraints)


def test_commute_minutes_enforced() -> None:
    constraints = _constraints(max_commute_minutes=20)
    assert not passes_hard_constraints(_job(commute_minutes=45), constraints)
    assert passes_hard_constraints(_job(commute_minutes=15), constraints)
