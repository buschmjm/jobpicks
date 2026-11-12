"""Unit tests for queue builder pure functions (E2.8)."""

from __future__ import annotations

from datetime import UTC, datetime

from core.constraints import HardConstraints
from core.queue_builder import (
    BACKFILL_WINDOW_MAX_DAYS,
    BACKFILL_WINDOW_PREFERRED_DAYS,
    QUEUE_EXPIRY_DAYS,
    QueueItemSnapshot,
    apply_daily_cap,
    build_backfill_deck,
    build_topup_deck,
    choose_backfill_window_days,
    find_expirable_items,
    interleave_explore,
    is_job_expired,
    select_explore_jobs,
    sort_by_score_desc,
    within_backfill_window,
)
from core.types import JobFeatures, RemoteMode, ScoredJob, ScoringConfig


def _job(
    job_id: str,
    *,
    score: float = 0.5,
    age_days: float = 7.0,
    salary_min: float | None = 120_000,
    remote: RemoteMode = RemoteMode.REMOTE,
    is_closed: bool = False,
    job_family: str | None = "platform",
    industry: str | None = None,
    components: dict[str, float] | None = None,
) -> ScoredJob:
    features = JobFeatures(
        job_id=job_id,
        title=f"Job {job_id}",
        company_id=f"co-{job_id}",
        company_name=f"Company {job_id}",
        salary_min=salary_min,
        remote_mode=remote,
        is_closed=is_closed,
        age_days=age_days,
        job_family=job_family,
        industry=industry,
        country="US",
        location_text="Austin, TX",
        skills=frozenset({"python"}),
    )
    default_components = {"title": 0.2, "skill": 0.1, "semantic": score}
    return ScoredJob(
        job=features,
        score=score,
        components={**default_components, **(components or {})},
    )


def _constraints(min_salary: float = 100_000) -> HardConstraints:
    return HardConstraints(min_salary=min_salary)


class TestBackfillOrdering:
    def test_sorts_by_score_descending(self) -> None:
        jobs = [_job("a", score=0.3), _job("b", score=0.9), _job("c", score=0.6)]
        ranked = sort_by_score_desc(jobs)
        assert [j.job.job_id for j in ranked] == ["b", "c", "a"]

    def test_backfill_orders_by_score_then_interleaves_explore(self) -> None:
        jobs = [
            _job("core-1", score=0.95, job_family="platform"),
            _job("core-2", score=0.90, job_family="platform"),
            _job("core-3", score=0.85, job_family="platform"),
            _job("core-4", score=0.80, job_family="platform"),
            _job("core-5", score=0.75, job_family="platform"),
            _job("core-6", score=0.70, job_family="platform"),
            _job("core-7", score=0.65, job_family="platform"),
            _job("core-8", score=0.60, job_family="platform"),
            _job("core-9", score=0.55, job_family="platform"),
            _job("explore-1", score=0.88, job_family="security"),
            _job("explore-2", score=0.82, job_family="security"),
        ]
        config = ScoringConfig(explore_slot_ratio=0.10)
        deck = build_backfill_deck(
            jobs,
            excluded_job_ids=set(),
            constraints=_constraints(),
            facet_exposure={"platform": 50, "security": 1},
            config=config,
        )

        assert deck[0].job.job_id == "core-1"
        assert deck[0].slot_type == "core"
        explore_positions = [i for i, item in enumerate(deck, start=1) if item.slot_type == "explore"]
        assert explore_positions
        assert any(pos % 10 == 0 for pos in explore_positions)

    def test_backfill_excludes_existing_and_outside_window(self) -> None:
        jobs = [
            _job("keep", score=0.9, age_days=10),
            _job("old", score=0.95, age_days=65),
            _job("dup", score=0.99, age_days=5),
        ]
        deck = build_backfill_deck(
            jobs,
            excluded_job_ids={"dup"},
            constraints=_constraints(),
            window_days=BACKFILL_WINDOW_MAX_DAYS,
        )
        ids = {item.job.job_id for item in deck}
        assert ids == {"keep"}

    def test_choose_backfill_window_prefers_30_days_when_enough_jobs(self) -> None:
        jobs = [_job(f"job-{index}", score=0.9 - index * 0.001, age_days=10) for index in range(120)]
        window = choose_backfill_window_days(
            jobs,
            excluded_job_ids=set(),
            constraints=_constraints(),
            config=ScoringConfig(backfill_deck_cap=100, backfill_max_jobs_per_employer=120),
        )
        assert window == BACKFILL_WINDOW_PREFERRED_DAYS

    def test_choose_backfill_window_falls_back_to_max_days(self) -> None:
        jobs = [
            _job("recent", score=0.9, age_days=10),
            _job("older", score=0.85, age_days=25),
        ]
        window = choose_backfill_window_days(
            jobs,
            excluded_job_ids=set(),
            constraints=_constraints(),
            config=ScoringConfig(backfill_deck_cap=100),
        )
        assert window == BACKFILL_WINDOW_MAX_DAYS

    def test_topup_drops_below_min_match_score(self) -> None:
        jobs = [
            _job("high", score=0.50),
            _job("border", score=0.43),
            _job("low", score=0.20),
        ]
        deck, _ = build_topup_deck(
            jobs,
            excluded_job_ids=set(),
            constraints=_constraints(),
            config=ScoringConfig(daily_topup_cap=30),
        )
        ids = {item.job.job_id for item in deck}
        assert ids == {"high", "border"}

    def test_backfill_core_excludes_below_min_match(self) -> None:
        jobs = [
            _job("good", score=0.45),
            _job("weak", score=0.30),
        ]
        deck = build_backfill_deck(
            jobs,
            excluded_job_ids=set(),
            constraints=_constraints(),
            config=ScoringConfig(explore_slot_ratio=0.0, backfill_deck_cap=100),
        )
        assert [item.job.job_id for item in deck] == ["good"]

    def test_backfill_applies_hard_constraints(self) -> None:
        jobs = [
            _job("ok", score=0.9, salary_min=150_000),
            _job("low-pay", score=0.99, salary_min=50_000),
        ]
        deck = build_backfill_deck(
            jobs,
            excluded_job_ids=set(),
            constraints=_constraints(min_salary=100_000),
        )
        assert [item.job.job_id for item in deck] == ["ok"]

    def test_within_backfill_window_respects_cutoff(self) -> None:
        job = _job("x", age_days=20).job
        assert within_backfill_window(job, window_days=28)
        old = _job("y", age_days=29).job
        assert not within_backfill_window(old, window_days=28)


class TestDailyCap:
    def test_apply_daily_cap_limits_results(self) -> None:
        jobs = [_job(str(i), score=float(i)) for i in range(50)]
        ranked = sort_by_score_desc(jobs)
        capped, dropped = apply_daily_cap(ranked, 30)
        assert len(capped) == 30
        assert dropped == 20

    def test_topup_applies_scoring_config_cap(self) -> None:
        jobs = [_job(str(i), score=0.45 + float(i) / 1000) for i in range(40)]
        config = ScoringConfig(daily_topup_cap=30)
        deck, dropped = build_topup_deck(
            jobs,
            excluded_job_ids=set(),
            constraints=_constraints(),
            config=config,
        )
        assert len(deck) == 30
        assert dropped == 10
        assert deck[0].score >= deck[-1].score

    def test_topup_excludes_existing_jobs(self) -> None:
        jobs = [_job("a", score=0.90), _job("b", score=0.80)]
        deck, _ = build_topup_deck(
            jobs,
            excluded_job_ids={"a"},
            constraints=_constraints(),
            config=ScoringConfig(daily_topup_cap=30),
        )
        assert [item.job.job_id for item in deck] == ["b"]


class TestExploreInterleave:
    def test_interleave_inserts_explore_every_tenth(self) -> None:
        core = [_job(f"c{i}", score=1.0 - i * 0.01) for i in range(9)]
        explore = [_job("e1", score=0.5)]
        deck = interleave_explore(core, explore, interval=10)
        assert len(deck) == 10
        assert deck[9].slot_type == "explore"
        assert deck[9].job.job_id == "e1"
        assert all(deck[i].slot_type == "core" for i in range(9))

    def test_select_explore_prefers_under_shown_facets(self) -> None:
        ranked = sort_by_score_desc(
            [
                _job("p1", score=0.9, job_family="platform"),
                _job("p2", score=0.85, job_family="platform"),
                _job("s1", score=0.88, job_family="security"),
                _job("s2", score=0.84, job_family="security"),
            ]
        )
        core, explore = select_explore_jobs(
            ranked,
            {"platform": 100, "security": 0},
            explore_ratio=0.25,
        )
        assert explore
        assert all(_primary_facet(j) == "security" for j in explore)
        explore_ids = {j.job.job_id for j in explore}
        assert explore_ids.isdisjoint({j.job.job_id for j in core})


def _primary_facet(job: ScoredJob) -> str:
    from core.queue_builder import _primary_facet as pf

    return pf(job)


class TestExpiry:
    def test_is_job_expired_when_closed(self) -> None:
        job = _job("x", is_closed=True).job
        assert is_job_expired(job, expiry_days=QUEUE_EXPIRY_DAYS)

    def test_is_job_expired_when_older_than_expiry_window(self) -> None:
        job = _job("x", age_days=61).job
        assert is_job_expired(job, expiry_days=QUEUE_EXPIRY_DAYS)

    def test_find_expirable_items_only_queued(self) -> None:
        now = datetime(2026, 8, 27, tzinfo=UTC)
        items = [
            QueueItemSnapshot(
                queue_id="q1",
                job_id="j1",
                state="queued",
                job=_job("j1", age_days=30, is_closed=False).job,
            ),
            QueueItemSnapshot(
                queue_id="q2",
                job_id="j2",
                state="swiped_right",
                job=_job("j2", age_days=30).job,
            ),
            QueueItemSnapshot(
                queue_id="q3",
                job_id="j3",
                state="queued",
                job=_job("j3", age_days=5).job,
            ),
            QueueItemSnapshot(
                queue_id="q4",
                job_id="j4",
                state="queued",
                job=_job("j4", age_days=5, is_closed=True).job,
            ),
        ]
        expired = find_expirable_items(items, expiry_days=28, now=now)
        assert set(expired) == {"q1", "q4"}

    def test_find_expirable_uses_reference_date(self) -> None:
        job = JobFeatures(
            job_id="j1",
            title="t",
            company_id="c",
            company_name="c",
            age_days=0,
        )
        item = QueueItemSnapshot(
            queue_id="q1",
            job_id="j1",
            state="queued",
            job=job,
        )
        old = datetime(2026, 7, 1, tzinfo=UTC)
        now = datetime(2026, 8, 27, tzinfo=UTC)
        expired = find_expirable_items(
            [item],
            expiry_days=28,
            now=now,
            reference_by_job={"j1": old},
        )
        assert expired == ["q1"]
