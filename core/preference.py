"""Preference learning from swipe feedback (§10). Deterministic, no DB."""

from __future__ import annotations

import math
from datetime import UTC, datetime

from core.constraints import passes_hard_constraints
from core.scoring import score_jobs
from core.types import (
    FeedbackAction,
    FeedbackEvent,
    HardConstraints,
    JobFeatures,
    PreferenceState,
    RejectionReason,
    ScoredJob,
    ScoringConfig,
    SessionState,
    UserProfile,
    effective_hard_constraints,
    facet_key,
    job_facet_map,
)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def time_decay_weight(event_age_days: float, half_life_days: float) -> float:
    if half_life_days <= 0:
        return 1.0
    return float(0.5 ** (event_age_days / half_life_days))


def _direction_for_action(action: FeedbackAction) -> str | None:
    if action in {FeedbackAction.SWIPE_RIGHT, FeedbackAction.TODO_APPLIED}:
        return "positive"
    if action in {FeedbackAction.SWIPE_LEFT, FeedbackAction.SKIP, FeedbackAction.EXPIRED_UNSWIPED}:
        return "negative"
    return None


def _base_signal_strength(event: FeedbackEvent, config: ScoringConfig) -> float:
    strengths = config.base_signal_strength
    if event.action == FeedbackAction.SWIPE_LEFT and event.reason is not None:
        return strengths.get(FeedbackAction.SWIPE_LEFT.value + "_with_reason", -0.7)
    return strengths.get(event.action.value, 0.0)


def compute_event_weight(
    event: FeedbackEvent,
    session: SessionState,
    config: ScoringConfig,
    now: datetime | None = None,
) -> float:
    """Apply time decay, dwell penalty, and mindless-swiping guard."""
    now = now or datetime.now(UTC)
    age_days = (now - event.timestamp).total_seconds() / 86400.0
    weight = _base_signal_strength(event, config)
    weight *= time_decay_weight(age_days, config.signal_half_life_days)

    if event.dwell_seconds is not None and event.dwell_seconds < config.min_dwell_seconds:
        weight *= config.low_dwell_weight_multiplier

    direction = _direction_for_action(event.action)
    if direction and session.same_direction_streak > config.mindless_streak_threshold:
        excess = session.same_direction_streak - config.mindless_streak_threshold
        weight *= config.mindless_streak_decay**excess

    return weight


def _reset_daily_delta_if_needed(profile: UserProfile, now: datetime) -> None:
    today = now.date().isoformat()
    if profile.daily_weight_delta_date != today:
        profile.daily_weight_delta_date = today
        profile.daily_weight_delta_used = 0.0


def _apply_clamped_delta(
    profile: UserProfile,
    config: ScoringConfig,
    delta: float,
    now: datetime,
) -> float:
    """Return the delta actually applied after per-event and per-day clamps."""
    _reset_daily_delta_if_needed(profile, now)
    clamped = _clamp(delta, -config.max_weight_delta_per_event, config.max_weight_delta_per_event)
    remaining = config.max_weight_delta_per_day - profile.daily_weight_delta_used
    if remaining <= 0:
        return 0.0
    if abs(clamped) > remaining:
        clamped = math.copysign(remaining, clamped)
    profile.daily_weight_delta_used += abs(clamped)
    return clamped


def _update_session(session: SessionState, event: FeedbackEvent) -> None:
    direction = _direction_for_action(event.action)
    if direction is None:
        return
    if session.last_direction == direction:
        session.same_direction_streak += 1
    else:
        session.same_direction_streak = 1
        session.last_direction = direction


def _update_taste_vector(
    state: PreferenceState,
    job: JobFeatures,
    weight: float,
    sign: float,
) -> None:
    if not job.embedding:
        return
    dim = len(job.embedding)
    if sign > 0:
        if not state.taste_positive_sum:
            state.taste_positive_sum = [0.0] * dim
        for i, v in enumerate(job.embedding):
            state.taste_positive_sum[i] += v * weight
        state.taste_positive_weight += weight
    else:
        if not state.taste_negative_sum:
            state.taste_negative_sum = [0.0] * dim
        for i, v in enumerate(job.embedding):
            state.taste_negative_sum[i] += v * weight
        state.taste_negative_weight += weight

    pos = state.taste_positive_sum
    pos_w = state.taste_positive_weight
    neg = state.taste_negative_sum
    neg_w = state.taste_negative_weight

    centroid = tuple(v / pos_w for v in pos) if pos_w > 0 else None

    if neg_w > 0 and centroid is not None:
        neg_centroid = tuple(v / neg_w for v in neg)
        scale = 0.5
        centroid = tuple(c - scale * n for c, n in zip(centroid, neg_centroid, strict=True))
    elif neg_w > 0:
        centroid = tuple(-0.5 * v / neg_w for v in neg)

    state.profile.taste_embedding = centroid


def _bump_facet_weights(
    profile: UserProfile,
    job: JobFeatures,
    delta: float,
    config: ScoringConfig,
    now: datetime,
) -> None:
    for category, value in job_facet_map(job).items():
        key = facet_key(category, value) if ":" not in category else f"{category}:{value}"
        if category.startswith("stack:"):
            key = facet_key("stack", value)
        applied = _apply_clamped_delta(profile, config, delta, now)
        if applied == 0.0:
            continue
        profile.learned_facet_weights[key] = profile.learned_facet_weights.get(key, 0.0) + applied


def _record_facet_exposure(profile: UserProfile, job: JobFeatures) -> None:
    for category, value in job_facet_map(job).items():
        key = facet_key(category, value) if ":" not in category else f"{category}:{value}"
        profile.facet_exposure_counts[key] = profile.facet_exposure_counts.get(key, 0) + 1


def apply_feedback(
    state: PreferenceState,
    event: FeedbackEvent,
    config: ScoringConfig,
    now: datetime | None = None,
) -> PreferenceState:
    """Apply one feedback event and return the mutated state."""
    now = now or datetime.now(UTC)
    _update_session(state.session, event)
    weight = compute_event_weight(event, state.session, config, now)
    profile = state.profile
    job = event.job

    if event.action == FeedbackAction.SWIPE_RIGHT:
        profile.right_swipe_count += 1
        _update_taste_vector(state, job, abs(weight), sign=1.0)
        _bump_facet_weights(profile, job, abs(weight) * 0.05, config, now)

    elif event.action == FeedbackAction.TODO_APPLIED:
        _update_taste_vector(state, job, abs(weight), sign=1.0)
        _bump_facet_weights(profile, job, abs(weight) * 0.08, config, now)

    elif event.action == FeedbackAction.SWIPE_LEFT:
        if event.reason == RejectionReason.COMPANY:
            profile.blocked_companies = frozenset(profile.blocked_companies | {job.company_id, job.company_name})
        elif event.reason == RejectionReason.NOT_QUALIFIED:
            gap = max(0, job.seniority_level - profile.seniority_level)
            if gap > 0:
                key = "seniority"
                d = _apply_clamped_delta(profile, config, abs(weight) * 0.04 * gap, now)
                profile.qualification_gap_penalties[key] = profile.qualification_gap_penalties.get(key, 0.0) + d
            for skill in job.skills - profile.skills:
                d = _apply_clamped_delta(profile, config, abs(weight) * 0.03, now)
                profile.qualification_gap_penalties[f"skill:{skill}"] = (
                    profile.qualification_gap_penalties.get(f"skill:{skill}", 0.0) + d
                )
        elif event.reason == RejectionReason.COMP_TOO_LOW:
            salary = job.salary_max or job.salary_min
            if salary is not None:
                floor = profile.effective_salary_floor or profile.target_salary
                bump = max(salary * 1.05, floor * 1.02)
                profile.effective_salary_floor = bump
        elif event.reason == RejectionReason.LOCATION_REMOTE:
            d = _apply_clamped_delta(profile, config, abs(weight) * 0.05, now)
            profile.geo_weight_multiplier = _clamp(profile.geo_weight_multiplier + d, 0.5, 2.0)
        elif event.reason == RejectionReason.DONT_WANT_THIS_WORK:
            _update_taste_vector(state, job, abs(weight), sign=-1.0)
            _bump_facet_weights(profile, job, -abs(weight) * 0.08, config, now)
        elif event.reason == RejectionReason.OVERQUALIFIED:
            d = _apply_clamped_delta(profile, config, abs(weight) * 0.04, now)
            profile.seniority_floor = min(profile.seniority_level, profile.seniority_floor + int(max(1, d * 10)))
        else:
            _update_taste_vector(state, job, abs(weight) * 0.3, sign=-1.0)

    elif event.action in {FeedbackAction.SKIP, FeedbackAction.EXPIRED_UNSWIPED}:
        _update_taste_vector(state, job, abs(weight) * 0.5, sign=-1.0)

    elif event.action == FeedbackAction.TODO_ARCHIVED:
        _bump_facet_weights(profile, job, weight * 0.03, config, now)

    _record_facet_exposure(profile, job)
    state.feedback_history.append(event)
    return state


def reverse_feedback(
    state: PreferenceState,
    event: FeedbackEvent,
    prior_action: FeedbackAction,
    config: ScoringConfig,
    now: datetime | None = None,
) -> PreferenceState:
    """Partially undo a prior swipe when the user changes their decision."""
    now = now or datetime.now(UTC)
    job = event.job
    if prior_action == FeedbackAction.SWIPE_RIGHT:
        state.profile.right_swipe_count = max(0, state.profile.right_swipe_count - 1)
        _update_taste_vector(state, job, 0.4, sign=-1.0)
        _bump_facet_weights(state.profile, job, -0.02, config, now)
    elif prior_action in {FeedbackAction.SWIPE_LEFT, FeedbackAction.SKIP, FeedbackAction.EXPIRED_UNSWIPED}:
        _update_taste_vector(state, job, 0.25, sign=1.0)
    return state


def _underrepresented_facet(profile: UserProfile) -> str | None:
    if not profile.facet_exposure_counts:
        return None
    return min(profile.facet_exposure_counts, key=lambda k: profile.facet_exposure_counts[k])


def select_explore_jobs(
    scored: list[ScoredJob],
    profile: UserProfile,
    config: ScoringConfig,
    count: int,
) -> list[ScoredJob]:
    """
    Pick ~explore_slot_ratio candidates: high semantic similarity from under-shown facets.
    """
    if not scored or count <= 0:
        return []

    under = _underrepresented_facet(profile)
    candidates: list[ScoredJob] = []
    for item in scored:
        facets = job_facet_map(item.job)
        facet_keys = {
            facet_key(cat, val) if ":" not in cat else f"{cat}:{val}"
            for cat, val in facets.items()
        }
        exposure = sum(profile.facet_exposure_counts.get(k, 0) for k in facet_keys)
        sem = item.components.get("semantic", 0.0)
        if sem >= 0.55 and (under is None or under in facet_keys or exposure <= 1):
            candidates.append(item)

    candidates.sort(key=lambda s: (s.components.get("semantic", 0.0), s.score), reverse=True)
    explore: list[ScoredJob] = []
    seen: set[str] = set()
    for item in candidates:
        if item.job.job_id in seen:
            continue
        seen.add(item.job.job_id)
        explore.append(
            ScoredJob(
                job=item.job,
                score=item.score,
                slot_type="explore",
                components=dict(item.components),
            )
        )
        if len(explore) >= count:
            break
    return explore


def apply_per_employer_cap(
    ranked: list[ScoredJob],
    session: SessionState,
    config: ScoringConfig,
    *,
    limit: int | None = None,
) -> list[ScoredJob]:
    """Max deck cards per employer per day."""
    capped: list[ScoredJob] = []
    counts = dict(session.employer_counts_today)
    limit = limit if limit is not None else config.max_jobs_per_employer_per_day
    for item in ranked:
        employer = item.job.company_id
        if counts.get(employer, 0) >= limit:
            continue
        counts[employer] = counts.get(employer, 0) + 1
        capped.append(item)
    session.employer_counts_today = counts
    return capped


def interleave_explore_slots(
    core: list[ScoredJob],
    explore: list[ScoredJob],
    config: ScoringConfig,
) -> list[ScoredJob]:
    """Insert one explore pick roughly every 1/explore_slot_ratio positions."""
    if not explore or config.explore_slot_ratio <= 0:
        return list(core)

    interval = max(1, round(1.0 / config.explore_slot_ratio))
    result: list[ScoredJob] = []
    explore_idx = 0
    for i, item in enumerate(core):
        if (i + 1) % interval == 0 and explore_idx < len(explore):
            result.append(explore[explore_idx])
            explore_idx += 1
        result.append(item)
    return result


def build_recommendations(
    state: PreferenceState,
    jobs: list[JobFeatures],
    constraints: HardConstraints,
    config: ScoringConfig,
    limit: int | None = None,
) -> list[ScoredJob]:
    """
    Score, cap employers, interleave explore slots.
    Hard-constraint violations are filtered before scoring — they never surface.
    """
    merged = effective_hard_constraints(state.profile, constraints)
    eligible = [j for j in jobs if passes_hard_constraints(j, merged)]
    scored = score_jobs(state.profile, eligible, config, merged)

    cap = limit or config.daily_topup_cap
    explore_count = max(1, int(cap * config.explore_slot_ratio)) if cap > 0 else 0
    explore = select_explore_jobs(scored, state.profile, config, explore_count)

    core_ids = {e.job.job_id for e in explore}
    core = [s for s in scored if s.job.job_id not in core_ids]

    interleaved = interleave_explore_slots(core[:cap], explore, config)
    return apply_per_employer_cap(interleaved, state.session, config)[:cap]
