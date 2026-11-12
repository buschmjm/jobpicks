"""Tests for core.preference — feedback learning and recommendation safety."""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

import pytest
from core.constraints import passes_hard_constraints
from core.preference import (
    apply_feedback,
    apply_per_employer_cap,
    build_recommendations,
    compute_event_weight,
    interleave_explore_slots,
    select_explore_jobs,
    time_decay_weight,
)
from core.scoring import score_jobs
from core.types import (
    FeedbackAction,
    FeedbackEvent,
    HardConstraints,
    JobFeatures,
    PreferenceState,
    RejectionReason,
    RemoteMode,
    ScoredJob,
    ScoringConfig,
    SessionState,
    UserProfile,
    effective_hard_constraints,
)


def _job(
    job_id: str,
    *,
    salary: float = 150_000,
    remote: RemoteMode = RemoteMode.REMOTE,
    company_id: str = "co",
    industry: str | None = "tech",
    embedding: tuple[float, ...] | None = (1.0, 0.0),
) -> JobFeatures:
    return JobFeatures(
        job_id=job_id,
        title=f"Job {job_id}",
        company_id=company_id,
        company_name=f"Company {company_id}",
        salary_min=salary,
        salary_max=salary,
        remote_mode=remote,
        industry=industry,
        embedding=embedding,
        skills=frozenset({"python", "linux"}),
        job_family="platform",
        country="US",
        location_text="Austin, TX",
    )


def _event(
    action: FeedbackAction,
    job: JobFeatures,
    *,
    reason: RejectionReason | None = None,
    dwell: float | None = 3.0,
    age_days: float = 0.0,
) -> FeedbackEvent:
    ts = datetime.now(UTC) - timedelta(days=age_days)
    return FeedbackEvent(
        user_id="u1",
        job_id=job.job_id,
        action=action,
        timestamp=ts,
        job=job,
        reason=reason,
        dwell_seconds=dwell,
    )


class TestEventWeight:
    def test_time_decay_halves_at_half_life(self) -> None:
        assert time_decay_weight(30.0, 30.0) == pytest.approx(0.5)

    def test_low_dwell_halves_weight(self) -> None:
        config = ScoringConfig()
        session = SessionState()
        job = _job("j1")
        heavy = compute_event_weight(_event(FeedbackAction.SWIPE_RIGHT, job, dwell=3.0), session, config)
        light = compute_event_weight(_event(FeedbackAction.SWIPE_RIGHT, job, dwell=0.5), session, config)
        assert light == pytest.approx(heavy * config.low_dwell_weight_multiplier)

    def test_mindless_streak_decays(self) -> None:
        config = ScoringConfig()
        session = SessionState(same_direction_streak=20, last_direction="positive")
        job = _job("j1")
        base_session = SessionState()
        decayed = compute_event_weight(_event(FeedbackAction.SWIPE_RIGHT, job), session, config)
        base = compute_event_weight(_event(FeedbackAction.SWIPE_RIGHT, job), base_session, config)
        assert decayed < base


class TestFeedbackLearning:
    def test_swipe_right_increments_count_and_taste(self) -> None:
        state = PreferenceState(profile=UserProfile(user_id="u1"))
        job = _job("j1", embedding=(1.0, 0.0))
        apply_feedback(state, _event(FeedbackAction.SWIPE_RIGHT, job), ScoringConfig())
        assert state.profile.right_swipe_count == 1
        assert state.profile.taste_embedding is not None

    def test_comp_too_low_raises_floor(self) -> None:
        state = PreferenceState(profile=UserProfile(user_id="u1", target_salary=120_000))
        job = _job("j1", salary=100_000)
        apply_feedback(
            state,
            _event(FeedbackAction.SWIPE_LEFT, job, reason=RejectionReason.COMP_TOO_LOW),
            ScoringConfig(),
        )
        assert state.profile.effective_salary_floor is not None
        assert state.profile.effective_salary_floor >= 100_000

    def test_company_reason_blocklists(self) -> None:
        state = PreferenceState(profile=UserProfile(user_id="u1"))
        job = _job("j1", company_id="badco")
        apply_feedback(
            state,
            _event(FeedbackAction.SWIPE_LEFT, job, reason=RejectionReason.COMPANY),
            ScoringConfig(),
        )
        assert "badco" in state.profile.blocked_companies

    def test_dont_want_work_negative_facet(self) -> None:
        state = PreferenceState(profile=UserProfile(user_id="u1"))
        job = _job("j1")
        apply_feedback(
            state,
            _event(FeedbackAction.SWIPE_LEFT, job, reason=RejectionReason.DONT_WANT_THIS_WORK),
            ScoringConfig(),
        )
        assert any(v < 0 for v in state.profile.learned_facet_weights.values()) or state.profile.taste_embedding


class TestExplorationAndCaps:
    def test_explore_selects_semantic_candidates(self) -> None:
        profile = UserProfile(user_id="u1", facet_exposure_counts={"job_family:platform": 5})
        scored = [
            ScoredJob(_job("a"), 0.9, components={"semantic": 0.8}),
            ScoredJob(_job("b"), 0.7, components={"semantic": 0.3}),
        ]
        explore = select_explore_jobs(scored, profile, ScoringConfig(), count=1)
        assert len(explore) == 1
        assert explore[0].slot_type == "explore"

    def test_interleave_inserts_explore(self) -> None:
        core = [ScoredJob(_job(f"c{i}"), 0.9 - i * 0.01) for i in range(10)]
        explore = [ScoredJob(_job("x"), 0.5, slot_type="explore")]
        mixed = interleave_explore_slots(core, explore, ScoringConfig(explore_slot_ratio=0.1))
        assert any(s.slot_type == "explore" for s in mixed)

    def test_per_employer_cap(self) -> None:
        session = SessionState()
        ranked = [ScoredJob(_job(f"j{i}", company_id="same"), 0.9) for i in range(5)]
        capped = apply_per_employer_cap(ranked, session, ScoringConfig(max_jobs_per_employer_per_day=3))
        assert len(capped) == 3


class TestHardConstraintProperty:
    """Property: hard-constraint violations never surface in recommendations."""

    REMOTES = [RemoteMode.REMOTE, RemoteMode.HYBRID, RemoteMode.ONSITE, RemoteMode.UNKNOWN]
    INDUSTRIES = ["tech", "finance", "healthcare", "retail", None]

    def _random_constraints(self, rng: random.Random) -> HardConstraints:
        min_salary = rng.choice([None, 80_000, 100_000, 120_000, 150_000])
        allowed = frozenset(rng.sample(self.REMOTES, k=rng.randint(1, len(self.REMOTES))))
        blocked = frozenset(rng.sample(["gambling", "tobacco", "crypto"], k=rng.randint(0, 2)))
        return HardConstraints(
            min_salary=min_salary,
            allowed_remote_modes=allowed,
            blocked_industries=blocked,
            home_lat=37.77,
            home_lon=-122.42,
            max_commute_radius_miles=rng.choice([None, 25.0, 50.0]),
        )

    def _random_job(self, rng: random.Random, i: int) -> JobFeatures:
        return JobFeatures(
            job_id=f"job-{i}",
            title=f"Title {i}",
            company_id=f"company-{rng.randint(0, 5)}",
            company_name=f"Co {i}",
            salary_min=rng.choice([None, 60_000, 90_000, 120_000, 160_000]),
            salary_max=rng.choice([None, 80_000, 110_000, 140_000, 180_000]),
            remote_mode=rng.choice(self.REMOTES),
            industry=rng.choice(self.INDUSTRIES),
            is_closed=rng.random() < 0.05,
            lat=37.77 + rng.uniform(-2, 2),
            lon=-122.42 + rng.uniform(-2, 2),
            embedding=(rng.random(), rng.random()),
            skills=frozenset(rng.sample(["python", "go", "k8s", "terraform", "linux"], k=3)),
        )

    def test_recommendations_never_violate_hard_constraints(self) -> None:
        rng = random.Random(42)
        config = ScoringConfig(daily_topup_cap=20)

        for trial in range(50):
            constraints = self._random_constraints(rng)
            profile = UserProfile(
                user_id=f"user-{trial}",
                target_salary=rng.choice([100_000, 130_000, 160_000]),
                blocked_companies=frozenset(rng.sample(["company-0", "company-1"], k=rng.randint(0, 1))),
            )
            merged = effective_hard_constraints(profile, constraints)
            jobs = [self._random_job(rng, i) for i in range(40)]
            state = PreferenceState(profile=profile)

            recs = build_recommendations(state, jobs, constraints, config, limit=15)
            for rec in recs:
                assert passes_hard_constraints(rec.job, merged), (
                    f"trial={trial} job={rec.job.job_id} violated hard constraints"
                )

            scored = score_jobs(profile, jobs, config, merged)
            for item in scored:
                assert passes_hard_constraints(item.job, merged)

    def test_blocked_company_never_recommended(self) -> None:
        constraints = HardConstraints(min_salary=100_000, allowed_remote_modes=frozenset({RemoteMode.REMOTE}))
        profile = UserProfile(user_id="u1", blocked_companies=frozenset({"evil-corp"}))
        jobs = [
            _job("good", company_id="goodco", salary=150_000),
            _job("bad", company_id="evil-corp", salary=150_000),
        ]
        state = PreferenceState(profile=profile)
        recs = build_recommendations(state, jobs, constraints, ScoringConfig(), limit=10)
        assert all(r.job.company_id != "evil-corp" for r in recs)
        assert any(r.job.company_id == "goodco" for r in recs)
