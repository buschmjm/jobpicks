"""Tests for core.scoring."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from core.constraints import filter_hard_constraints, passes_hard_constraints
from core.scoring import (
    comp_fit,
    cosine_similarity,
    effective_weights,
    jaccard,
    passes_core_relevance,
    score_job,
    score_jobs,
    seniority_fit,
    title_fit,
)
from core.types import HardConstraints, JobFeatures, RemoteMode, ScoredJob, ScoringConfig, UserProfile

FIXTURES = Path(__file__).parent / "fixtures" / "scoring_golden.json"
_US_JOB_DEFAULTS = {"country": "US", "location_text": "Austin, TX"}


def _job_from_dict(data: dict) -> JobFeatures:
    return JobFeatures(
        job_id=data["job_id"],
        title=data["title"],
        company_id=data["company_id"],
        company_name=data["company_name"],
        embedding=tuple(data["embedding"]) if data.get("embedding") else None,
        skills=frozenset(data.get("skills", [])),
        salary_min=data.get("salary_min"),
        salary_max=data.get("salary_max"),
        seniority_level=data.get("seniority_level", 2),
        remote_mode=RemoteMode(data.get("remote_mode", "unknown")),
        country=data.get("country", "US"),
        location_text=data.get("location_text", "Austin, TX"),
    )


def _profile_from_dict(data: dict) -> UserProfile:
    return UserProfile(
        user_id=data["user_id"],
        skills=frozenset(data.get("skills", [])),
        seniority_level=data.get("seniority_level", 2),
        target_salary=data.get("target_salary", 100_000),
        taste_embedding=tuple(data["taste_embedding"]) if data.get("taste_embedding") else None,
        right_swipe_count=data.get("right_swipe_count", 0),
    )


class TestScoringPrimitives:
    def test_cosine_identical(self) -> None:
        assert cosine_similarity((1.0, 0.0), (1.0, 0.0)) == pytest.approx(1.0)

    def test_cosine_orthogonal(self) -> None:
        assert cosine_similarity((1.0, 0.0), (0.0, 1.0)) == pytest.approx(0.0)

    def test_jaccard_full_overlap(self) -> None:
        assert jaccard(frozenset({"a", "b"}), frozenset({"a", "b"})) == pytest.approx(1.0)

    def test_jaccard_partial(self) -> None:
        assert jaccard(frozenset({"a", "b"}), frozenset({"b", "c"})) == pytest.approx(1 / 3)

    def test_comp_fit_at_target(self) -> None:
        job = JobFeatures(
            job_id="j",
            title="t",
            company_id="c",
            company_name="C",
            salary_min=140_000,
            salary_max=160_000,
            **_US_JOB_DEFAULTS,
        )
        assert comp_fit(job, 140_000) == pytest.approx(1.0)

    def test_comp_fit_below_target(self) -> None:
        job = JobFeatures(
            job_id="j",
            title="t",
            company_id="c",
            company_name="C",
            salary_max=70_000,
            **_US_JOB_DEFAULTS,
        )
        assert comp_fit(job, 140_000) == pytest.approx(0.5)

    def test_seniority_fit_match(self) -> None:
        assert seniority_fit(2, 2) == pytest.approx(1.0)

    def test_seniority_fit_underqualified(self) -> None:
        assert seniority_fit(2, 4) == pytest.approx(0.5)

    def test_seniority_fit_unknown_returns_neutral(self) -> None:
        assert seniority_fit(2, 4, job_seniority_known=False) == pytest.approx(0.5)

    def test_comp_fit_unknown_salary_is_low(self) -> None:
        job = JobFeatures(
            job_id="j",
            title="t",
            company_id="c",
            company_name="C",
            **_US_JOB_DEFAULTS,
        )
        assert comp_fit(job, 140_000) == pytest.approx(0.15)

    def test_title_fit_rejects_unrelated_attorney_role(self) -> None:
        targets = (
            "technical program manager",
            "business systems analyst",
            "product operations manager",
        )
        assert title_fit("attorney", targets) == pytest.approx(0.0)
        assert title_fit("Associate Attorney", targets) < 0.12

    def test_passes_core_relevance_requires_title_or_skill(self) -> None:
        config = ScoringConfig(min_title_fit_for_core=0.12)
        semantic_only = ScoredJob(
            job=JobFeatures(
                job_id="j",
                title="Attorney",
                company_id="c",
                company_name="C",
                **_US_JOB_DEFAULTS,
            ),
            score=0.5,
            components={"title": 0.0, "skill": 0.0, "semantic": 0.8},
        )
        title_match = ScoredJob(
            job=semantic_only.job,
            score=0.5,
            components={"title": 0.2, "skill": 0.0, "semantic": 0.8},
        )
        skill_match = ScoredJob(
            job=semantic_only.job,
            score=0.5,
            components={"title": 0.0, "skill": 0.1, "semantic": 0.8},
        )
        assert passes_core_relevance(semantic_only, config) is False
        assert passes_core_relevance(title_match, config) is True
        assert passes_core_relevance(skill_match, config) is True

    def test_effective_weights_redistribute_when_skill_coverage_low(self) -> None:
        config = ScoringConfig(skill_coverage_ratio=0.0)
        weights = effective_weights(config, UserProfile(user_id="u", right_swipe_count=0))
        assert weights["w_skill"] == pytest.approx(0.0)
        assert weights["w_sem"] > ScoringConfig().cold_start_w_sem


class TestColdStartBlend:
    def test_ramps_semantic_weight(self) -> None:
        config = ScoringConfig()
        w0 = effective_weights(config, UserProfile(user_id="u", right_swipe_count=0))
        w20 = effective_weights(config, UserProfile(user_id="u", right_swipe_count=20))
        assert w0["w_sem"] < w20["w_sem"]
        assert w0["w_skill"] > w20["w_skill"]
        assert w0["w_title"] > w20["w_title"]
        for weights in (w0, w20):
            total = sum(weights[k] for k in ("w_sem", "w_skill", "w_title", "w_comp", "w_level", "w_geo"))
            assert total == pytest.approx(1.0)


class TestGoldenCases:
    @pytest.fixture(scope="class")
    def golden_cases(self) -> list[dict]:
        return json.loads(FIXTURES.read_text())["cases"]

    @pytest.mark.parametrize("case_index", range(4))
    def test_golden_score_ranges(self, golden_cases: list[dict], case_index: int) -> None:
        case = golden_cases[case_index]
        profile = _profile_from_dict(case["profile"])
        job = _job_from_dict(case["job"])
        config = ScoringConfig()
        constraints_data = case.get("constraints", {})
        constraints = HardConstraints(
            min_salary=constraints_data.get("min_salary"),
            allowed_remote_modes=frozenset({RemoteMode.REMOTE, RemoteMode.HYBRID, RemoteMode.ONSITE}),
        )

        result = score_job(profile, job, config, constraints)

        if case.get("expect_none"):
            assert result is None
            return

        assert result is not None
        assert case["expected_min_score"] <= result.score <= case["expected_max_score"]


class TestHardConstraintFiltering:
    def test_filter_removes_low_salary(self) -> None:
        jobs = [
            JobFeatures(
                job_id="low",
                title="Low",
                company_id="c1",
                company_name="C1",
                salary_max=80_000,
                remote_mode=RemoteMode.REMOTE,
                **_US_JOB_DEFAULTS,
            ),
            JobFeatures(
                job_id="ok",
                title="Ok",
                company_id="c2",
                company_name="C2",
                salary_max=150_000,
                remote_mode=RemoteMode.REMOTE,
                **_US_JOB_DEFAULTS,
            ),
        ]
        constraints = HardConstraints(min_salary=120_000, allowed_remote_modes=frozenset({RemoteMode.REMOTE}))
        filtered = filter_hard_constraints(jobs, constraints)
        assert [j.job_id for j in filtered] == ["ok"]

    def test_score_jobs_never_includes_failures(self) -> None:
        profile = UserProfile(user_id="u", skills=frozenset({"python"}))
        jobs = [
            JobFeatures(
                job_id="blocked",
                title="Blocked",
                company_id="c",
                company_name="C",
                salary_max=50_000,
                remote_mode=RemoteMode.ONSITE,
                **_US_JOB_DEFAULTS,
            ),
            JobFeatures(
                job_id="good",
                title="Good",
                company_id="c2",
                company_name="C2",
                salary_max=150_000,
                remote_mode=RemoteMode.REMOTE,
                skills=frozenset({"python"}),
                **_US_JOB_DEFAULTS,
            ),
        ]
        constraints = HardConstraints(
            min_salary=100_000,
            allowed_remote_modes=frozenset({RemoteMode.REMOTE}),
        )
        scored = score_jobs(profile, jobs, ScoringConfig(), constraints)
        assert all(passes_hard_constraints(s.job, constraints) for s in scored)
        assert {s.job.job_id for s in scored} == {"good"}
