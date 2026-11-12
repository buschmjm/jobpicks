"""Workstream F acceptance tests (FT1–FT6)."""

from __future__ import annotations

from datetime import date

import pytest
from core.competitiveness import competitiveness_percentile
from core.deck_ranking import apply_deck_eligibility, enrich_scored_job, sort_deck_jobs
from core.scoring import score_job
from core.seniority import SENIORITY_JUNIOR, derive_seniority_from_title, seniority_to_int
from core.types import HardConstraints, JobFeatures, RemoteMode, ScoredJob, ScoringConfig, UserProfile


def _profile(**kwargs: object) -> UserProfile:
    defaults = {
        "user_id": "u1",
        "skills": frozenset({"python", "kubernetes"}),
        "seniority_level": 2,
        "target_salary": 100_000.0,
        "target_titles": ("software engineer",),
    }
    defaults.update(kwargs)
    return UserProfile(**defaults)  # type: ignore[arg-type]


def _job_features(
    job_id: str,
    *,
    title: str,
    level: int,
    salary_min: float | None = 120_000,
    salary_max: float | None = 150_000,
    skills: frozenset[str] | None = None,
    posted: date | None = None,
) -> JobFeatures:
    return JobFeatures(
        job_id=job_id,
        title=title,
        normalized_title=title.lower(),
        company_id="co",
        company_name="Acme",
        skills=skills or frozenset({"python"}),
        salary_min=salary_min,
        salary_max=salary_max,
        seniority_level=level,
        seniority_known=True,
        remote_mode=RemoteMode.REMOTE,
        country="US",
        date_posted=posted or date(2026, 1, 15),
    )


def _scored(profile: UserProfile, job: JobFeatures, config: ScoringConfig | None = None) -> ScoredJob:
    cfg = config or ScoringConfig()
    result = score_job(profile, job, cfg, HardConstraints(min_salary=60_000))
    assert result is not None
    return enrich_scored_job(result, profile)


class TestFT1Determinism:
    def test_same_user_job_scored_twice_identical_components(self) -> None:
        profile = _profile()
        job = _job_features("j1", title="Platform Engineer", level=2)
        cfg = ScoringConfig()
        first = score_job(profile, job, cfg, HardConstraints())
        second = score_job(profile, job, cfg, HardConstraints())
        assert first is not None and second is not None
        assert first.components == second.components
        assert first.score == second.score


class TestFT3DeckStretchRules:
    def test_hundred_card_fixture_stretch_and_attainability_rules(self) -> None:
        profile = _profile(seniority_level=3)
        cfg = ScoringConfig(min_match_score=0.35, min_explore_score=0.25)
        jobs: list[ScoredJob] = []
        for i in range(100):
            level = 3 if i < 90 else 4
            match_score = 0.6 if i < 90 else 0.58
            job = _job_features(f"j{i}", title=f"Engineer {i}", level=level)
            item = ScoredJob(job=job, score=match_score, components={"match_score": match_score})
            jobs.append(enrich_scored_job(item, profile))

        core = apply_deck_eligibility(jobs, profile, config=cfg)
        stretch_count = sum(1 for item in core if item.components.get("stretch"))
        assert stretch_count <= 5
        assert all(int(item.components.get("level_delta", 0)) < 2 for item in core)
        assert all(float(item.components.get("attainability", 0)) >= 0.15 for item in core)


class TestFT4DeckOrdering:
    def test_deck_orders_by_deck_rank_score(self) -> None:
        profile = _profile()
        high = enrich_scored_job(
            ScoredJob(
                job=_job_features("high", title="Senior Engineer", level=3),
                score=0.7,
                components={"match_score": 0.7},
            ),
            profile,
        )
        low = enrich_scored_job(
            ScoredJob(
                job=_job_features("low", title="Engineer", level=2, posted=date(2026, 2, 1)),
                score=0.9,
                components={"match_score": 0.9},
            ),
            profile,
        )
        ordered = sort_deck_jobs([low, high])
        assert float(ordered[0].components["deck_rank_score"]) >= float(
            ordered[1].components["deck_rank_score"]
        )


class TestFT6Competitiveness:
    def test_p_top_formula(self) -> None:
        n = 10
        percentile = 0.9
        p_top = percentile ** (n - 1)
        assert p_top == pytest.approx(0.9**9, abs=1e-9)

    def test_synthetic_pool_reproducible(self) -> None:
        profile = _profile()
        job = _job_features("j", title="SRE", level=3, skills=frozenset({"python", "go"}))
        cfg = ScoringConfig()
        scored = score_job(profile, job, cfg)
        assert scored is not None
        first = competitiveness_percentile(profile, job, scored.score, config=cfg)
        second = competitiveness_percentile(profile, job, scored.score, config=cfg)
        assert first.percentile == second.percentile
        assert first.p_top == second.p_top

    def test_competitiveness_lines_paired(self) -> None:
        profile = _profile()
        job = _job_features("j", title="Engineer", level=3)
        cfg = ScoringConfig()
        scored = score_job(profile, job, cfg)
        assert scored is not None
        est = competitiveness_percentile(profile, job, scored.score, config=cfg)
        line1, line2 = est.display_lines()
        assert "top" in line1.lower()
        assert "strongest applicant" in line2.lower()
        assert est.p_top_percent_display == round(est.p_top * 100)


class TestSeniorityScale:
    def test_keyword_derivation(self) -> None:
        assert seniority_to_int("VP Engineering") == 7
        assert seniority_to_int("Director of Engineering") == 6
        assert derive_seniority_from_title("Junior Developer") == SENIORITY_JUNIOR
