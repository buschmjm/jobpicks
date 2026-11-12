"""Build domain UserProfile from ORM rows (shared by deck service and queue builder)."""

from __future__ import annotations

from typing import Any

from core.models import HardConstraints, PreferenceWeights, Profile
from core.seniority import seniority_to_int
from core.types import RemoteMode, RemoteOpenness, UserProfile


def _home_coords(
    profile: Profile,
    hard_constraints: HardConstraints | None = None,
) -> tuple[float | None, float | None]:
    if hard_constraints and hard_constraints.locations:
        hc_first = hard_constraints.locations[0]
        if isinstance(hc_first, dict):
            lat, lon = hc_first.get("lat"), hc_first.get("lon")
            return (
                float(lat) if lat is not None else None,
                float(lon) if lon is not None else None,
            )
    if not profile.locations:
        return None, None
    loc_first = profile.locations[0]
    if isinstance(loc_first, dict):
        lat, lon = loc_first.get("lat"), loc_first.get("lon")
        return (
            float(lat) if lat is not None else None,
            float(lon) if lon is not None else None,
        )
    return None, None


def _preferred_remote_modes(
    profile: Profile,
    hard_constraints: HardConstraints | None,
) -> frozenset[RemoteMode]:
    if hard_constraints and hard_constraints.remote_openness:
        try:
            openness = RemoteOpenness(hard_constraints.remote_openness)
        except ValueError:
            openness = RemoteOpenness.OPEN_TO_REMOTE
        if openness == RemoteOpenness.REMOTE_ONLY:
            return frozenset({RemoteMode.REMOTE})
        if openness == RemoteOpenness.LOCAL_ONLY:
            return frozenset({RemoteMode.HYBRID, RemoteMode.ONSITE, RemoteMode.UNKNOWN})
        return frozenset({RemoteMode.REMOTE, RemoteMode.HYBRID, RemoteMode.ONSITE, RemoteMode.UNKNOWN})

    remote_pref = profile.remote_preference or "remote"
    try:
        if remote_pref == "any":
            return frozenset(
                {RemoteMode.REMOTE, RemoteMode.HYBRID, RemoteMode.ONSITE, RemoteMode.UNKNOWN}
            )
        return frozenset({RemoteMode(remote_pref)})
    except ValueError:
        return frozenset({RemoteMode.REMOTE})


def user_profile_from_orm(
    profile: Profile,
    weights: PreferenceWeights | None,
    *,
    hard_constraints: HardConstraints | None = None,
) -> UserProfile:
    stored: dict[str, Any] = weights.weights if weights and weights.weights else {}
    preferred = _preferred_remote_modes(profile, hard_constraints)

    learned_taste = tuple(weights.taste_embedding) if weights and weights.taste_embedding else None
    profile_prior = tuple(profile.taste_embedding) if profile.taste_embedding else None
    if profile_prior is None:
        profile_prior = tuple(stored["profile_prior_embedding"]) if stored.get("profile_prior_embedding") else None

    home_lat, home_lon = _home_coords(profile, hard_constraints)
    target_salary = float(profile.salary_target_min or 100_000)
    if hard_constraints and hard_constraints.min_salary is not None:
        target_salary = max(target_salary, float(hard_constraints.min_salary))

    stated = dict(stored.get("stated_facet_weights") or {})

    return UserProfile(
        user_id=str(profile.user_id),
        skills=frozenset(s.lower() for s in (profile.skills or [])),
        seniority_level=seniority_to_int(
            profile.seniority_int if profile.seniority_int is not None else profile.seniority_level
        ),
        target_salary=target_salary,
        taste_embedding=learned_taste,
        profile_prior_embedding=profile_prior,
        target_titles=tuple(t.lower() for t in (profile.target_titles or [])),
        stated_facet_weights=stated,
        learned_facet_weights=dict(stored.get("learned_facet_weights") or {}),
        home_lat=home_lat,
        home_lon=home_lon,
        preferred_remote_modes=preferred,
        effective_salary_floor=stored.get("effective_salary_floor"),
        seniority_floor=int(stored.get("seniority_floor") or 0),
        qualification_gap_penalties=dict(stored.get("qualification_gap_penalties") or {}),
        geo_weight_multiplier=float(stored.get("geo_weight_multiplier") or 1.0),
        right_swipe_count=weights.right_swipe_count if weights else 0,
        blocked_companies=frozenset(stored.get("blocked_companies") or []),
        facet_exposure_counts=dict(stored.get("facet_exposure_counts") or {}),
        daily_weight_delta_used=float(stored.get("daily_weight_delta_used") or 0.0),
        daily_weight_delta_date=stored.get("daily_weight_delta_date"),
    )
