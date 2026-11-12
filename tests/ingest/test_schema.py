"""Tests for StandardJob schema."""

from datetime import UTC, date, datetime

import pytest
from ingest.schema import EmploymentType, SalaryInfo, StandardJob, WorkArrangement


def test_standard_job_core_fields() -> None:
    job = StandardJob(
        title="Platform Engineer",
        company="Acme",
        location="Remote",
        remote=True,
        latitude=37.7,
        longitude=-122.4,
        employment_type=EmploymentType.FULL_TIME,
        salary=SalaryInfo(min_amount=140000, max_amount=170000),
        date_posted=date(2026, 8, 20),
        description="Build platforms.",
        requirements="5+ years K8s",
        source="jsearch",
        source_url="https://example.com/apply",
        collected_timestamp=datetime(2026, 8, 27, tzinfo=UTC),
        work_arrangement=WorkArrangement.REMOTE,
        seniority_level="senior",
        required_technologies=("Kubernetes", "Terraform"),
    )
    assert job.remote is True
    assert job.salary is not None
    assert job.salary.min_amount == 140000


def test_remote_none_means_unknown() -> None:
    job = StandardJob(
        title="SRE",
        company="Globex",
        location="Chicago, IL",
        remote=None,
        date_posted=date(2026, 8, 15),
        description="Hybrid role.",
        source="jsearch",
        source_url="https://example.com",
        collected_timestamp=datetime(2026, 8, 27, tzinfo=UTC),
    )
    assert job.remote is None
    assert job.work_arrangement == WorkArrangement.UNKNOWN


def test_empty_title_rejected() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        StandardJob(
            title="   ",
            company="Acme",
            location="Remote",
            date_posted=date(2026, 8, 20),
            description="Desc",
            source="adzuna",
            source_url="https://example.com",
            collected_timestamp=datetime(2026, 8, 27, tzinfo=UTC),
        )
