"""Ranking-quality and matching pipeline tests from algorithm audit."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from core.models import Company, Job, JobStatus
from core.models import RemoteMode as OrmRemoteMode
from core.models import ScoringConfig as ScoringConfigRow
from core.preference import apply_feedback, apply_per_employer_cap
from core.preference_store import preference_state_from_stored, serialize_preference_state
from core.queue_builder import build_backfill_deck, job_features_from_orm
from core.scoring import score_job, score_jobs, title_fit
from core.scoring_config_loader import scoring_config_from_db_rows
from core.types import (
    FeedbackAction,
    FeedbackEvent,
    HardConstraints,
    JobFeatures,
    RemoteMode,
    ScoredJob,
    ScoringConfig,
    SessionState,
    UserProfile,
)


def _job(
    job_id: str,
    *,
    title: str = "Platform Engineer",
    normalized_title: str | None = None,
    embedding: tuple[float, ...] | None = (1.0, 0.0, 0.0),
    company_id: str = "co1",
    salary: float = 150_000,
    age_days: float = 1.0,
) -> JobFeatures:
    return JobFeatures(
        job_id=job_id,
        title=title,
        normalized_title=normalized_title or title.lower(),
        company_id=company_id,
        company_name=f"Co {company_id}",
        embedding=embedding,
        skills=frozenset({"python", "linux"}),
        salary_min=salary,
        salary_max=salary,
        remote_mode=RemoteMode.REMOTE,
        industry="tech",
        job_family="platform",
        age_days=age_days,
        country="US",
        location_text="Austin, TX",
    )


def _event(action: FeedbackAction, job: JobFeatures) -> FeedbackEvent:
    return FeedbackEvent(
        user_id="u1",
        job_id=job.job_id,
        action=action,
        timestamp=datetime.now(UTC),
        job=job,
    )


class TestTasteAccumulation:
    def test_three_swipes_accumulate_not_last_only(self) -> None:
        profile = UserProfile(user_id="u1")
        state = preference_state_from_stored(profile, {})
        jobs = [
            _job("j1", embedding=(1.0, 0.0, 0.0)),
            _job("j2", embedding=(0.0, 1.0, 0.0)),
            _job("j3", embedding=(0.0, 0.0, 1.0)),
        ]
        for job in jobs:
            apply_feedback(state, _event(FeedbackAction.SWIPE_RIGHT, job), ScoringConfig())

        assert state.taste_positive_weight == pytest.approx(3 * 0.8)
        assert len(state.taste_positive_sum) == 3
        assert state.profile.taste_embedding is not None
        assert state.profile.taste_embedding[0] == pytest.approx(1.0 / 3, abs=0.01)
        assert state.profile.taste_embedding[1] == pytest.approx(1.0 / 3, abs=0.01)

        roundtrip = preference_state_from_stored(profile, serialize_preference_state(state))
        assert roundtrip.taste_positive_weight == state.taste_positive_weight


class TestTitleFit:
    def test_sre_title_ranks_above_unrelated(self) -> None:
        profile = UserProfile(
            user_id="u1",
            target_titles=("site reliability engineer",),
            skills=frozenset({"python"}),
        )
        sre = _job("sre", title="Site Reliability Engineer", normalized_title="site reliability engineer")
        sales = _job("sales", title="Account Executive", normalized_title="account executive")
        config = ScoringConfig()
        constraints = HardConstraints(allowed_remote_modes=frozenset({RemoteMode.REMOTE}))

        sre_score = score_job(profile, sre, config, constraints)
        sales_score = score_job(profile, sales, config, constraints)
        assert sre_score is not None and sales_score is not None
        assert sre_score.score > sales_score.score
        assert title_fit("site reliability engineer", profile.target_titles) > 0.5


class TestProfilePriorSemantic:
    def test_prior_embedding_boosts_similar_job(self) -> None:
        profile = UserProfile(
            user_id="u1",
            profile_prior_embedding=(1.0, 0.0),
            skills=frozenset({"python"}),
        )
        similar = _job("sim", embedding=(1.0, 0.0))
        orthogonal = _job("orth", embedding=(0.0, 1.0))
        config = ScoringConfig()
        constraints = HardConstraints(allowed_remote_modes=frozenset({RemoteMode.REMOTE}))

        sim_score = score_job(profile, similar, config, constraints)
        orth_score = score_job(profile, orthogonal, config, constraints)
        assert sim_score is not None and orth_score is not None
        assert sim_score.score > orth_score.score


class TestJobFeaturesOrm:
    def test_maps_company_industry_and_job_family(self) -> None:
        company = Company(
            id=uuid.uuid4(),
            name="Acme",
            normalized_name="acme",
            industry="fintech",
            size_band="500-1000",
        )
        job = Job(
            company_id=company.id,
            company=company,
            company_name="Acme",
            title="Backend Engineer",
            normalized_title="backend engineer",
            canonical_hash="hash-orm",
            status=JobStatus.OPEN,
            remote_mode=OrmRemoteMode.REMOTE,
            location_text="Austin, TX",
            country="US",
            skills=["Python", "Go"],
            source_url="https://example.com/job",
        )
        features = job_features_from_orm(job)
        assert features.industry == "fintech"
        assert features.company_size == "500-1000"
        assert features.job_family == "backend engineer"
        assert "python" in features.skills


class TestScoringConfigLoader:
    def test_migration_seed_shape_round_trip(self) -> None:
        rows = [
            ScoringConfigRow(
                key="score_weights",
                value={
                    "w_sem": 0.35,
                    "w_skill": 0.25,
                    "w_comp": 0.15,
                    "w_level": 0.15,
                    "w_geo": 0.10,
                },
            ),
            ScoringConfigRow(key="feedback_half_life_days", value={"days": 30}),
            ScoringConfigRow(key="cold_start_right_swipe_threshold", value={"count": 20}),
            ScoringConfigRow(key="daily_queue_topup_cap", value={"count": 30}),
            ScoringConfigRow(key="explore_slot_ratio", value={"ratio": 0.1}),
            ScoringConfigRow(
                key="mindless_swipe_guard",
                value={"streak_threshold": 15, "min_dwell_seconds": 1.5},
            ),
        ]
        config = scoring_config_from_db_rows(rows)
        assert config.w_sem == pytest.approx(0.35)
        assert config.signal_half_life_days == pytest.approx(30)
        assert config.cold_start_right_swipe_threshold == 20
        assert config.daily_topup_cap == 30
        assert config.explore_slot_ratio == pytest.approx(0.1)
        assert config.mindless_streak_threshold == 15


class TestEmployerCapInBackfill:
    def test_same_company_capped_in_deck(self) -> None:
        profile = UserProfile(user_id="u1", right_swipe_count=25)
        scored = [
            ScoredJob(
                job=_job(f"j{i}", company_id="same_co", salary=150_000 - i, age_days=1.0),
                score=1.0 - i * 0.01,
            )
            for i in range(10)
        ]
        deck = build_backfill_deck(
            scored,
            excluded_job_ids=set(),
            constraints=HardConstraints(allowed_remote_modes=frozenset({RemoteMode.REMOTE})),
            profile=profile,
            config=ScoringConfig(
                max_jobs_per_employer_per_day=3,
                backfill_max_jobs_per_employer=3,
                backfill_deck_cap=100,
            ),
            employer_counts={},
        )
        employers = [item.job.company_id for item in deck]
        assert employers.count("same_co") <= 3

    def test_apply_per_employer_cap_helper(self) -> None:
        ranked = [_job(f"j{i}", company_id="co") for i in range(5)]
        scored = [
            score_jobs(
                UserProfile(user_id="u"),
                [job],
                ScoringConfig(max_jobs_per_employer_per_day=3),
                HardConstraints(allowed_remote_modes=frozenset({RemoteMode.REMOTE})),
            )[0]
            for job in ranked
        ]
        session = SessionState()
        capped = apply_per_employer_cap(scored, session, ScoringConfig(max_jobs_per_employer_per_day=3))
        assert len(capped) == 3
