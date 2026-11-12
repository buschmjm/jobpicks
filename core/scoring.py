"""Deterministic candidate↔job scoring (§10). No LLM."""

from __future__ import annotations

import math
import re

from core.constraints import filter_hard_constraints, passes_hard_constraints
from core.types import (
    HardConstraints,
    JobFeatures,
    RemoteMode,
    ScoredJob,
    ScoringConfig,
    UserProfile,
    effective_hard_constraints,
    facet_key,
    job_facet_map,
)


def cosine_similarity(a: tuple[float, ...] | None, b: tuple[float, ...] | None) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return max(-1.0, min(1.0, dot / (norm_a * norm_b)))


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _tokenize_title(text: str) -> frozenset[str]:
    tokens = re.findall(r"[a-z0-9+#]+", text.lower())
    return frozenset(t for t in tokens if len(t) > 1)


_TITLE_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "at",
        "for",
        "in",
        "of",
        "or",
        "the",
        "to",
        "with",
        "i",
        "ii",
        "iii",
        "iv",
        "sr",
        "jr",
        "us",
        "u",
        "s",
    }
)

_TITLE_GENERIC = frozenset(
    {
        "manager",
        "engineer",
        "senior",
        "staff",
        "lead",
        "principal",
        "director",
        "analyst",
        "consultant",
        "specialist",
        "coordinator",
        "associate",
        "head",
        "vp",
        "remote",
    }
)


def _meaningful_title_tokens(text: str) -> frozenset[str]:
    tokens = _tokenize_title(text)
    return frozenset(t for t in tokens if t not in _TITLE_STOPWORDS and t not in _TITLE_GENERIC)


def title_fit(job_title: str, target_titles: tuple[str, ...]) -> float:
    """Overlap between job title and user's stated target roles."""
    if not target_titles:
        return 0.0
    job_tokens = _meaningful_title_tokens(job_title)
    if not job_tokens:
        return 0.0
    best = 0.0
    for target in target_titles:
        target_tokens = _meaningful_title_tokens(target)
        if not target_tokens:
            continue
        overlap_tokens = job_tokens & target_tokens
        if not overlap_tokens:
            continue
        overlap = len(overlap_tokens) / len(job_tokens | target_tokens)
        # Require at least one non-generic overlapping token, or two overlapping tokens.
        if len(overlap_tokens) >= 2 or any(token not in _TITLE_GENERIC for token in overlap_tokens):
            best = max(best, overlap)
    return best


def semantic_fit(profile: UserProfile, job: JobFeatures, config: ScoringConfig) -> float:
    """Blend profile prior and learned taste vectors; ramp learned weight with swipes."""
    threshold = config.cold_start_right_swipe_threshold
    t = min(1.0, profile.right_swipe_count / threshold) if threshold > 0 else 1.0

    prior_raw = cosine_similarity(profile.profile_prior_embedding, job.embedding)
    learned_raw = cosine_similarity(profile.taste_embedding, job.embedding)

    if profile.profile_prior_embedding and profile.taste_embedding:
        blended = (1.0 - t) * prior_raw + t * learned_raw
    elif profile.taste_embedding:
        blended = learned_raw
    elif profile.profile_prior_embedding:
        blended = prior_raw
    else:
        blended = 0.0

    return (blended + 1.0) / 2.0


def comp_fit(
    job: JobFeatures,
    user_target: float,
    effective_floor: float | None = None,
) -> float:
    """1.0 at/above target (or learned floor), linear decay below."""
    floor = effective_floor if effective_floor is not None else user_target
    salary = job.salary_max if job.salary_max is not None else job.salary_min
    if salary is None:
        return 0.15
    if salary >= floor:
        return 1.0
    if floor <= 0:
        return 0.0
    return max(0.0, salary / floor)


def seniority_fit(
    user_level: int,
    job_level: int,
    seniority_floor: int = 0,
    *,
    job_seniority_known: bool = True,
) -> float:
    if not job_seniority_known:
        return 0.5
    effective_user = max(user_level, seniority_floor)
    delta = job_level - effective_user
    if delta == 0:
        return 1.0
    if delta == 1:
        return 0.85
    if delta == -1:
        return 0.6
    if delta < -1:
        return max(0.0, 0.4 + delta * 0.15)
    return max(0.0, 1.0 - delta * 0.25)


def geo_fit(job: JobFeatures, profile: UserProfile) -> float:
    """Soft geo/remote preference after hard filters."""
    if job.remote_mode in profile.preferred_remote_modes:
        return 1.0
    if job.remote_mode == RemoteMode.UNKNOWN:
        return 0.5
    if RemoteMode.REMOTE in profile.preferred_remote_modes and job.remote_mode == RemoteMode.HYBRID:
        return 0.7
    if job.commute_minutes is not None:
        if job.commute_minutes <= 20:
            return 0.95
        if job.commute_minutes <= 45:
            return 0.75
        if job.commute_minutes <= 60:
            return 0.5
        return 0.25
    if job.remote_mode == RemoteMode.ONSITE and profile.home_lat is not None and profile.home_lon is not None:
        if job.lat is not None and job.lon is not None:
            from core.constraints import _haversine_miles

            distance = _haversine_miles(profile.home_lat, profile.home_lon, job.lat, job.lon)
            if distance <= 15:
                return 0.9
            if distance <= 40:
                return 0.6
            return 0.3
    return 0.2


def facet_boosts(job: JobFeatures, profile: UserProfile) -> float:
    """Learned + stated per-facet adjustments."""
    total = 0.0
    facets = job_facet_map(job)
    for category, value in facets.items():
        key = facet_key(category, value) if ":" not in category else f"{category}:{value}"
        if category.startswith("stack:"):
            key = facet_key("stack", value)
        stated = profile.stated_facet_weights.get(key, 0.0)
        learned = profile.learned_facet_weights.get(key, 0.0)
        total += stated + learned
    return total


def qualification_penalty(job: JobFeatures, profile: UserProfile) -> float:
    """Penalty from 'not qualified' feedback on skill/seniority gaps."""
    penalty = 0.0
    if job.seniority_level > profile.seniority_level:
        gap = job.seniority_level - profile.seniority_level
        penalty += profile.qualification_gap_penalties.get("seniority", 0.0) * gap
    missing = job.skills - profile.skills
    for skill in missing:
        penalty += profile.qualification_gap_penalties.get(f"skill:{skill}", 0.0)
    return penalty


def blend_weights(config: ScoringConfig, right_swipe_count: int) -> dict[str, float]:
    """Cold-start blend: ramp semantic and title weights in as labels accumulate."""
    threshold = config.cold_start_right_swipe_threshold
    t = min(1.0, right_swipe_count / threshold) if threshold > 0 else 1.0
    w_sem = config.cold_start_w_sem + (config.w_sem - config.cold_start_w_sem) * t
    w_skill = config.cold_start_w_skill + (config.w_skill - config.cold_start_w_skill) * t
    w_title = config.cold_start_w_title + (config.w_title - config.cold_start_w_title) * t
    return {
        "w_sem": w_sem,
        "w_skill": w_skill,
        "w_title": w_title,
        "w_comp": config.w_comp,
        "w_level": config.w_level,
        "w_geo": config.w_geo,
    }


def effective_weights(config: ScoringConfig, profile: UserProfile) -> dict[str, float]:
    weights = blend_weights(config, profile.right_swipe_count)
    weights["w_geo"] *= profile.geo_weight_multiplier

    coverage = config.skill_coverage_ratio
    if coverage < 0.5 and weights["w_skill"] > 0:
        skill_weight = weights["w_skill"]
        weights["w_skill"] = 0.0
        weights["w_sem"] += skill_weight * 0.55
        weights["w_title"] += skill_weight * 0.45

    total = sum(weights[k] for k in ("w_sem", "w_skill", "w_title", "w_comp", "w_level", "w_geo"))
    if total > 0:
        for key in ("w_sem", "w_skill", "w_title", "w_comp", "w_level", "w_geo"):
            weights[key] /= total
    return weights


def score_job(
    profile: UserProfile,
    job: JobFeatures,
    config: ScoringConfig,
    constraints: HardConstraints | None = None,
) -> ScoredJob | None:
    """
    Compute weighted hybrid score. Returns None if hard constraints fail.
    """
    merged = effective_hard_constraints(profile, constraints) if constraints else None
    if merged is not None and not passes_hard_constraints(job, merged):
        return None

    weights = effective_weights(config, profile)

    sem = semantic_fit(profile, job, config)
    title = title_fit(job.normalized_title or job.title, profile.target_titles)
    skill = jaccard(profile.skills, job.skills)
    comp = comp_fit(job, profile.target_salary, profile.effective_salary_floor)
    level = seniority_fit(
        profile.seniority_level,
        job.seniority_level,
        profile.seniority_floor,
        job_seniority_known=job.seniority_known,
    )
    geo = geo_fit(job, profile)
    facets = facet_boosts(job, profile)
    qual_penalty = qualification_penalty(job, profile)

    raw = (
        weights["w_sem"] * sem
        + weights["w_title"] * title
        + weights["w_skill"] * skill
        + weights["w_comp"] * comp
        + weights["w_level"] * level
        + weights["w_geo"] * geo
        + facets
        - qual_penalty
    )

    popularity_cap = min(job.popularity_score, 0.15)
    score = max(0.0, min(1.0, raw - popularity_cap))

    return ScoredJob(
        job=job,
        score=score,
        components={
            "semantic": sem,
            "title": title,
            "skill": skill,
            "comp": comp,
            "level": level,
            "geo": geo,
            "facet_boosts": facets,
            "qualification_penalty": qual_penalty,
            "popularity_cap": popularity_cap,
        },
    )


def score_jobs(
    profile: UserProfile,
    jobs: list[JobFeatures],
    config: ScoringConfig,
    constraints: HardConstraints,
) -> list[ScoredJob]:
    """Score all jobs that pass hard constraints; never include failing jobs."""
    merged = effective_hard_constraints(profile, constraints)
    eligible = filter_hard_constraints(jobs, merged)
    scored: list[ScoredJob] = []
    for job in eligible:
        result = score_job(profile, job, config, merged)
        if result is not None:
            scored.append(result)
    scored.sort(key=lambda s: s.score, reverse=True)
    return scored


def passes_core_relevance(item: ScoredJob, config: ScoringConfig) -> bool:
    """Core deck slots need title or skill overlap — semantic alone is insufficient."""
    components = item.components
    title = components.get("title", 0.0)
    skill = components.get("skill", 0.0)
    if title >= config.min_title_fit_for_core:
        return True
    return skill > 0.0
