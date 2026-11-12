"""Tests for ingest pipeline: normalize, dedupe, freshness."""

from datetime import UTC, date, datetime

from ingest.pipeline import (
    DedupeIndex,
    FreshnessConfig,
    FreshnessRegistry,
    IngestPipeline,
    SafetyNetFilter,
    normalize_job,
    simhash,
    source_tier,
)
from ingest.schema import StandardJob, WorkArrangement


def _sample_job(**overrides: object) -> StandardJob:
    base = dict(
        title="Platform Engineer",
        company="Acme Corp",
        location="San Francisco, CA",
        remote=True,
        date_posted=date(2026, 8, 20),
        description="Kubernetes and Terraform platform work.",
        source="adzuna",
        source_url="https://example.com/job/1",
        collected_timestamp=datetime(2026, 8, 27, tzinfo=UTC),
    )
    base.update(overrides)
    return StandardJob(**base)  # type: ignore[arg-type]


def test_normalize_job_sets_hashes_and_work_arrangement() -> None:
    job = normalize_job(_sample_job(remote=True))
    assert job.canonical_hash is not None
    assert job.description_simhash == simhash(job.description)
    assert job.work_arrangement == WorkArrangement.REMOTE


def test_dedupe_index_rejects_duplicates() -> None:
    index = DedupeIndex()
    first = normalize_job(_sample_job())
    second = normalize_job(_sample_job(description="Kubernetes and Terraform platform work."))

    assert index.add(first) is not None
    assert index.add(second) is None
    assert len(index) == 1


def test_canonical_hash_changes_with_title() -> None:
    job_a = normalize_job(_sample_job(title="Platform Engineer"))
    job_b = normalize_job(_sample_job(title="Site Reliability Engineer"))
    assert job_a.canonical_hash != job_b.canonical_hash


def test_safety_net_filters_old_jobs() -> None:
    pipeline = IngestPipeline(
        safety_net=SafetyNetFilter(max_days_old=28),
        freshness=FreshnessConfig(corpus_max_age_days=28),
    )
    old_job = _sample_job(date_posted=date(2026, 6, 1))
    accepted = pipeline.process_batch([old_job], reference_date=date(2026, 8, 27))
    assert accepted == []


def test_safety_net_remote_only_excludes_onsite() -> None:
    pipeline = IngestPipeline(
        safety_net=SafetyNetFilter(max_days_old=28, remote_only=True),
    )
    onsite = _sample_job(remote=False, date_posted=date(2026, 8, 20))
    accepted = pipeline.process_batch([onsite], reference_date=date(2026, 8, 27))
    assert accepted == []


def test_safety_net_us_only_excludes_international_jobs() -> None:
    pipeline = IngestPipeline(
        safety_net=SafetyNetFilter(max_days_old=28, us_only=True),
    )
    international = _sample_job(
        source="greenhouse",
        location="London, UK",
        date_posted=date(2026, 8, 20),
    )
    accepted = pipeline.process_batch([international], reference_date=date(2026, 8, 27))
    assert accepted == []


def test_is_recommendable_respects_14_day_window() -> None:
    pipeline = IngestPipeline(freshness=FreshnessConfig(recommend_max_age_days=14))
    recent = normalize_job(_sample_job(date_posted=date(2026, 8, 20)))
    stale = normalize_job(_sample_job(date_posted=date(2026, 8, 1)))

    assert pipeline.is_recommendable(recent, reference_date=date(2026, 8, 27))
    assert not pipeline.is_recommendable(stale, reference_date=date(2026, 8, 27))


def test_corpus_cutoff_is_60_days() -> None:
    pipeline = IngestPipeline()
    assert pipeline.corpus_cutoff(reference_date=date(2026, 8, 27)) == date(2026, 6, 28)


def test_source_tier_mapping() -> None:
    assert source_tier("greenhouse") == 2
    assert source_tier("adzuna") == 1
    assert source_tier("unknown") == 1


def test_dedupe_prefers_tier2_over_tier1() -> None:
    index = DedupeIndex()
    aggregator = normalize_job(
        _sample_job(source="adzuna", source_url="https://adzuna.com/job/1")
    )
    ats = normalize_job(
        _sample_job(source="greenhouse", source_url="https://boards.greenhouse.io/acme/jobs/1")
    )

    assert index.add(aggregator) is not None
    assert index.add(ats) is not None
    assert len(index) == 1
    stored = index.values()[0]
    assert stored.source == "greenhouse"


def test_dedupe_keeps_tier2_when_tier1_arrives_later() -> None:
    index = DedupeIndex()
    ats = normalize_job(
        _sample_job(source="lever", source_url="https://jobs.lever.co/acme/1")
    )
    aggregator = normalize_job(
        _sample_job(source="jsearch", source_url="https://jsearch.example/job/1")
    )

    assert index.add(ats) is not None
    assert index.add(aggregator) is None
    assert index.values()[0].source == "lever"


def test_freshness_registry_tracks_first_and_last_seen() -> None:
    registry = FreshnessRegistry()
    job = normalize_job(_sample_job())
    seen_at = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)

    states = registry.observe_batch([job], seen_at=seen_at)
    assert len(states) == 1
    state = states[0]
    assert state.first_seen == seen_at
    assert state.last_seen == seen_at
    assert state.status == "active"

    later = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)
    registry.observe_batch([job], seen_at=later)
    updated = registry.get(job.canonical_hash or "")
    assert updated is not None
    assert updated.first_seen == seen_at
    assert updated.last_seen == later


def test_freshness_registry_marks_closed_after_missed_crawls() -> None:
    registry = FreshnessRegistry(config=FreshnessConfig(closed_after_missed_crawls=3))
    job = normalize_job(_sample_job())
    registry.observe_batch([job], seen_at=datetime(2026, 8, 27, tzinfo=UTC))
    key = job.canonical_hash or ""

    registry.mark_missed_for_absent(set())
    registry.mark_missed_for_absent(set())
    changed = registry.mark_missed_for_absent(set())
    assert changed[0].status == "closed"
    assert registry.get(key) is not None
    assert registry.get(key).status == "closed"
