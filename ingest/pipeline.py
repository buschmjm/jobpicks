"""Ingest pipeline: normalize, safety-net filter, dedupe, freshness rules."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from ingest.country import is_us_job
from ingest.schema import StandardJob, WorkArrangement

SourceTier = Literal[1, 2, 3]

# Tier 2 = ATS-direct (preferred over aggregator copies); tier 1 = bulk aggregators.
SOURCE_TIER: dict[str, SourceTier] = {
    "adzuna": 1,
    "jsearch": 1,
    "remotive": 1,
    "greenhouse": 2,
    "lever": 2,
    "usajobs": 2,
}


def source_tier(source: str) -> SourceTier:
    """Return data-source tier; unknown sources default to tier 1."""
    return SOURCE_TIER.get(source, 1)


def normalize_text(value: str) -> str:
    """Lowercase, collapse whitespace, strip punctuation for hashing."""
    lowered = value.lower().strip()
    collapsed = re.sub(r"\s+", " ", lowered)
    return re.sub(r"[^\w\s]", "", collapsed)


def simhash(text: str, bits: int = 64) -> str:
    """Simple character n-gram simhash for description dedupe (plan §8)."""
    normalized = normalize_text(text)
    if not normalized:
        return "0" * (bits // 4)

    shingles: set[str] = set()
    window = 3
    padded = f"  {normalized}  "
    for index in range(len(padded) - window + 1):
        shingles.add(padded[index : index + window])

    vector = [0] * bits
    for shingle in shingles:
        digest = int(hashlib.md5(shingle.encode()).hexdigest(), 16)
        for bit in range(bits):
            vector[bit] += 1 if (digest >> bit) & 1 else -1

    fingerprint = 0
    for bit, weight in enumerate(vector):
        if weight > 0:
            fingerprint |= 1 << bit
    return f"{fingerprint:0{bits // 4}x}"


def canonical_hash(title: str, company: str, location: str, description: str) -> str:
    """Dedupe key: normalized title + company + location + description simhash."""
    parts = (
        normalize_text(title),
        normalize_text(company),
        normalize_text(location),
        simhash(description),
    )
    payload = "|".join(parts)
    return hashlib.sha256(payload.encode()).hexdigest()


def normalize_job(job: StandardJob) -> StandardJob:
    """Fill pipeline metadata and normalize work_arrangement from remote flag."""
    sim = simhash(job.description)
    canon = canonical_hash(job.title, job.company, job.location, job.description)

    work_arrangement = job.work_arrangement
    if work_arrangement == WorkArrangement.UNKNOWN and job.remote is not None:
        work_arrangement = WorkArrangement.REMOTE if job.remote else WorkArrangement.ONSITE

    return job.model_copy(
        update={
            "description_simhash": sim,
            "canonical_hash": canon,
            "work_arrangement": work_arrangement,
        }
    )


@dataclass(frozen=True)
class FreshnessConfig:
    """Rolling corpus and recommendation windows (plan §8, §5)."""

    corpus_max_age_days: int = 60
    recommend_max_age_days: int = 14
    closed_after_missed_crawls: int = 3


@dataclass
class SafetyNetFilter:
    """Re-filter jobs when APIs under-filter (plan §18 pitfalls)."""

    salary_min: int | None = None
    max_days_old: int = 60
    remote_only: bool | None = None
    us_only: bool = True

    def passes(self, job: StandardJob, *, reference_date: date | None = None) -> bool:
        today = reference_date or datetime.now(UTC).date()
        age_days = (today - job.date_posted).days
        if age_days > self.max_days_old:
            return False
        if age_days < 0:
            return False

        if self.us_only and not is_us_job(job):
            return False

        if self.salary_min is not None and job.salary is not None:
            effective_min = job.salary.min_amount
            if effective_min is not None and effective_min < self.salary_min:
                return False

        return not (self.remote_only is True and job.remote is False)


@dataclass
class DedupeIndex:
    """In-memory dedupe index; prefers higher-tier (ATS-direct) records on hash collision."""

    _seen: dict[str, StandardJob] = field(default_factory=dict)

    def add(self, job: StandardJob) -> StandardJob | None:
        """Return job if accepted; None if an equal-or-higher-tier duplicate exists."""
        key = job.canonical_hash
        if key is None:
            key = canonical_hash(job.title, job.company, job.location, job.description)
            job = job.model_copy(update={"canonical_hash": key})

        existing = self._seen.get(key)
        if existing is None:
            self._seen[key] = job
            return job

        if source_tier(job.source) > source_tier(existing.source):
            self._seen[key] = job
            return job
        return None

    def __len__(self) -> int:
        return len(self._seen)

    def values(self) -> list[StandardJob]:
        return list(self._seen.values())


@dataclass
class JobFreshnessState:
    """Track first_seen / last_seen / missed crawls for lifecycle (plan §8)."""

    first_seen: datetime
    last_seen: datetime
    missed_crawls: int = 0
    status: str = "active"  # active | closed
    canonical_hash: str | None = None
    primary_source: str | None = None

    def mark_seen(self, seen_at: datetime) -> None:
        self.last_seen = seen_at
        self.missed_crawls = 0
        if self.status == "closed":
            self.status = "active"

    def mark_missed_crawl(self) -> None:
        self.missed_crawls += 1

    def update_status(self, config: FreshnessConfig) -> None:
        if self.missed_crawls >= config.closed_after_missed_crawls:
            self.status = "closed"

    def to_persistence(self) -> dict[str, datetime | int | str | None]:
        """Serialize freshness fields for DB upsert (jobs.first_seen / last_seen / status)."""
        return {
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "status": self.status,
            "missed_crawls": self.missed_crawls,
            "primary_source": self.primary_source,
            "canonical_hash": self.canonical_hash,
        }


@dataclass
class FreshnessRegistry:
    """Track first_seen/last_seen across crawl batches for DB persistence."""

    config: FreshnessConfig = field(default_factory=FreshnessConfig)
    _states: dict[str, JobFreshnessState] = field(default_factory=dict)

    def observe_batch(
        self,
        jobs: list[StandardJob],
        *,
        seen_at: datetime | None = None,
    ) -> list[JobFreshnessState]:
        """Mark jobs as seen; return updated freshness states."""
        timestamp = seen_at or datetime.now(UTC)
        updated: list[JobFreshnessState] = []
        for job in jobs:
            key = job.canonical_hash
            if key is None:
                key = canonical_hash(job.title, job.company, job.location, job.description)
            state = self._states.get(key)
            if state is None:
                state = JobFreshnessState(
                    first_seen=timestamp,
                    last_seen=timestamp,
                    canonical_hash=key,
                    primary_source=job.source,
                )
                self._states[key] = state
            else:
                state.mark_seen(timestamp)
                if source_tier(job.source) >= source_tier(state.primary_source or ""):
                    state.primary_source = job.source
            updated.append(state)
        return updated

    def mark_missed_for_absent(self, seen_hashes: set[str]) -> list[JobFreshnessState]:
        """Increment missed crawls for indexed jobs not present in the latest batch."""
        changed: list[JobFreshnessState] = []
        for key, state in self._states.items():
            if key not in seen_hashes:
                state.mark_missed_crawl()
                state.update_status(self.config)
                changed.append(state)
        return changed

    def get(self, canonical_hash_key: str) -> JobFreshnessState | None:
        return self._states.get(canonical_hash_key)

    def persistence_rows(self) -> list[dict[str, datetime | int | str | None]]:
        """All freshness records ready for DB upsert."""
        return [state.to_persistence() for state in self._states.values()]


class IngestPipeline:
    """Orchestrates normalization, safety-net filtering, dedupe, and freshness checks."""

    def __init__(
        self,
        *,
        freshness: FreshnessConfig | None = None,
        safety_net: SafetyNetFilter | None = None,
    ) -> None:
        self.freshness = freshness or FreshnessConfig()
        self.safety_net = safety_net or SafetyNetFilter(
            max_days_old=self.freshness.corpus_max_age_days
        )
        self.dedupe = DedupeIndex()

    def process_batch(
        self,
        jobs: list[StandardJob],
        *,
        reference_date: date | None = None,
    ) -> list[StandardJob]:
        accepted: list[StandardJob] = []
        for raw in jobs:
            normalized = normalize_job(raw)
            if not self.safety_net.passes(normalized, reference_date=reference_date):
                continue
            unique = self.dedupe.add(normalized)
            if unique is not None:
                accepted.append(unique)
        return accepted

    def is_recommendable(self, job: StandardJob, *, reference_date: date | None = None) -> bool:
        """Jobs older than 14 days or outside corpus window must not be recommended."""
        today = reference_date or datetime.now(UTC).date()
        age = (today - job.date_posted).days
        if age > self.freshness.recommend_max_age_days:
            return False
        return not age > self.freshness.corpus_max_age_days

    def corpus_cutoff(self, *, reference_date: date | None = None) -> date:
        today = reference_date or datetime.now(UTC).date()
        return today - timedelta(days=self.freshness.corpus_max_age_days)
