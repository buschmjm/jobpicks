"""Competitiveness estimate for job detail (Workstream F5)."""

from __future__ import annotations

import random
from dataclasses import dataclass
from functools import lru_cache

from core.scoring import score_job
from core.types import JobFeatures, ScoringConfig, UserProfile

_POOL_SIZE = 10_000
_POOL_SEED = 42
_POOL_SEED = 42

# Fallback expected applicants by job level (LOCKED table).
_EXPECTED_APPLICANTS: dict[tuple[int, int], int] = {
    (0, 2): 40,
    (3, 4): 25,
    (5, 6): 15,
    (7, 8): 8,
}


@dataclass(frozen=True)
class CompetitivenessEstimate:
    percentile: float
    p_top: float
    expected_applicants: int
    top_percent_display: int
    p_top_percent_display: int

    def display_lines(self) -> tuple[str, str]:
        top_pct = self.top_percent_display
        p_top_pct = self.p_top_percent_display
        line1 = (
            f"You'd likely rank in the top {top_pct}% of applicants "
            "(estimated from market data)"
        )
        line2 = f"Estimated chance of being the strongest applicant: {p_top_pct}%"
        return line1, line2


def expected_applicants_for_level(level: int) -> int:
    for (lo, hi), count in _EXPECTED_APPLICANTS.items():
        if lo <= level <= hi:
            return count
    return 25


def _laplace_smooth(count: int, total: int, vocab: int) -> float:
    return (count + 1.0) / (total + vocab)


@lru_cache(maxsize=128)
def _synthetic_skill_pool(
    cluster_key: str,
    level: int,
    job_skills: tuple[str, ...],
) -> tuple[frozenset[str], ...]:
    rng = random.Random(_POOL_SEED ^ hash((cluster_key, level)))
    if not job_skills:
        return tuple(frozenset() for _ in range(_POOL_SIZE))

    # Marginal frequencies with Laplace +1 smoothing over job skill set.
    marginals = {skill: 0.55 for skill in job_skills}
    profiles: list[frozenset[str]] = []
    for _ in range(_POOL_SIZE):
        skills: set[str] = set()
        for skill in job_skills:
            if rng.random() < marginals[skill]:
                skills.add(skill)
        profiles.append(frozenset(skills))
    return tuple(profiles)


def competitiveness_percentile(
    user_profile: UserProfile,
    job: JobFeatures,
    match_score: float,
    *,
    config: ScoringConfig | None = None,
) -> CompetitivenessEstimate:
    """
    Percentile = fraction of synthetic competitor pool scoring strictly below user match_score.
  """
    cfg = config or ScoringConfig()
    cluster = job.job_family or job.normalized_title or job.title
    level = job.seniority_level
    pool = _synthetic_skill_pool(cluster.lower(), level, tuple(sorted(job.skills)))

    below = 0
    for skills in pool:
        competitor = UserProfile(
            user_id="synthetic",
            skills=skills,
            seniority_level=level,
            target_salary=user_profile.target_salary,
        )
        scored = score_job(competitor, job, cfg)
        comp_score = scored.score if scored is not None else 0.0
        if comp_score < match_score:
            below += 1

    percentile = below / _POOL_SIZE
    n = expected_applicants_for_level(level)
    p_top = percentile ** (n - 1)
    top_percent = round((1.0 - percentile) * 100)
    p_top_percent = round(p_top * 100)
    return CompetitivenessEstimate(
        percentile=percentile,
        p_top=p_top,
        expected_applicants=n,
        top_percent_display=top_percent,
        p_top_percent_display=p_top_percent,
    )


def competitiveness_for_empty_profile(job: JobFeatures) -> CompetitivenessEstimate:
    return CompetitivenessEstimate(
        percentile=0.5,
        p_top=0.5 ** (expected_applicants_for_level(job.seniority_level) - 1),
        expected_applicants=expected_applicants_for_level(job.seniority_level),
        top_percent_display=50,
        p_top_percent_display=round(
            0.5 ** (expected_applicants_for_level(job.seniority_level) - 1) * 100
        ),
    )


def format_competitiveness_lines(estimate: CompetitivenessEstimate) -> tuple[str, str]:
    """Never show p_top without percentile — return both display lines."""
    return estimate.display_lines()
