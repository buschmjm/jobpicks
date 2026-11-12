"""Deck ordering rules: deck_rank_score, stretch slots, attainability floor (F3)."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import TYPE_CHECKING

from core.attainability import (
    ATTAINABILITY_DECK_FLOOR,
    attainability,
    deck_rank_score,
)
from core.scoring import passes_core_relevance
from core.types import ScoredJob, ScoringConfig, UserProfile

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _job_date_posted(job_date: date | None, age_days: float) -> date:
    if job_date is not None:
        return job_date
    from datetime import UTC, datetime, timedelta

    return (datetime.now(tz=UTC) - timedelta(days=int(age_days or 0))).date()


def enrich_scored_job(
    item: ScoredJob,
    profile: UserProfile,
    *,
    session: Session | None = None,
) -> ScoredJob:
    """Attach match_score, attainability, deck_rank_score, and level_delta."""
    match = float(item.score)
    att = attainability(profile, item.job, session=session)
    rank = deck_rank_score(match, att)
    delta = item.job.seniority_level - profile.seniority_level
    components = dict(item.components)
    components["match_score"] = match
    components["attainability"] = att
    components["deck_rank_score"] = rank
    components["level_delta"] = float(delta)
    return replace(item, components=components)


def sort_deck_jobs(jobs: list[ScoredJob]) -> list[ScoredJob]:
    """Order by deck_rank_score DESC, tiebreak date_posted DESC."""

    def sort_key(item: ScoredJob) -> tuple[float, float, str]:
        posted = _job_date_posted(item.job.date_posted, item.job.age_days)
        posted_ord = float(posted.toordinal())
        rank = float(item.components.get("deck_rank_score", item.score))
        return (-rank, -posted_ord, item.job.job_id)

    return sorted(jobs, key=sort_key)


def apply_deck_eligibility(
    jobs: list[ScoredJob],
    profile: UserProfile,
    *,
    config: ScoringConfig,
) -> list[ScoredJob]:
    """D1/D2: attainability floor, no Δ≥+2, stretch cap ≤1 per 20."""
    _ = profile
    eligible: list[ScoredJob] = []
    stretch_candidates: list[ScoredJob] = []

    for item in jobs:
        if not passes_core_relevance(item, config):
            continue
        match = float(item.components.get("match_score", item.score))
        att = float(item.components.get("attainability", 1.0))
        delta = int(item.components.get("level_delta", 0))

        if att < ATTAINABILITY_DECK_FLOOR:
            continue
        if delta >= 2:
            continue
        if match < config.min_match_score:
            continue

        if delta == 1 and match >= 0.55:
            stretch_candidates.append(item)
            continue
        eligible.append(item)

    deck_size = len(eligible) + (1 if stretch_candidates else 0)
    max_stretch = max(1, deck_size // 20) if stretch_candidates else 0
    if max_stretch > 0 and stretch_candidates:
        best_stretch = max(
            stretch_candidates,
            key=lambda item: (
                float(item.components.get("deck_rank_score", item.score)),
                _job_date_posted(item.job.date_posted, item.job.age_days).toordinal(),
            ),
        )
        components = dict(best_stretch.components)
        components["stretch"] = 1.0
        eligible.append(replace(best_stretch, components=components))

    return sort_deck_jobs(eligible)


def build_deck_ranked_jobs(
    scored_jobs: list[ScoredJob],
    profile: UserProfile,
    *,
    session: Session | None = None,
    config: ScoringConfig | None = None,
) -> list[ScoredJob]:
    cfg = config or ScoringConfig()
    enriched = [enrich_scored_job(item, profile, session=session) for item in scored_jobs]
    return apply_deck_eligibility(enriched, profile, config=cfg)
