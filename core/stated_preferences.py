"""Derive stated facet weights and remote acceptability from preferences."""

from __future__ import annotations

from core.types import RemoteMode, RemoteOpenness, facet_key


def remote_acceptability_from_openness(openness: RemoteOpenness | str) -> dict[str, bool]:
    value = RemoteOpenness(openness) if isinstance(openness, str) else openness
    if value == RemoteOpenness.REMOTE_ONLY:
        return {"remote": True, "hybrid": False, "onsite": False}
    if value == RemoteOpenness.LOCAL_ONLY:
        return {"remote": False, "hybrid": True, "onsite": True}
    return {"remote": True, "hybrid": True, "onsite": True}


def stated_facet_weights_from_questionnaire(
    *,
    target_titles: list[str] | None,
    remote_preference: str | None = None,
    remote_openness: str | None = None,
    industries_to_avoid: list[str] | None,
) -> dict[str, float]:
    """Map onboarding choices to per-facet scoring boosts (plan §10 layer 2)."""
    weights: dict[str, float] = {}

    pref = remote_openness or remote_preference
    if pref:
        if pref in {"local_only", "onsite", "hybrid"}:
            try:
                mode = RemoteMode.HYBRID if pref == "local_only" else RemoteMode(pref)
                weights[facet_key("remote_mode", mode.value)] = 0.08
            except ValueError:
                pass
        elif pref in {"open_to_remote", "any"}:
            weights[facet_key("remote_mode", RemoteMode.REMOTE.value)] = 0.06
        elif pref == "remote_only" or pref == "remote":
            weights[facet_key("remote_mode", RemoteMode.REMOTE.value)] = 0.08

    for industry in industries_to_avoid or []:
        if industry.strip():
            weights[facet_key("industry", industry.strip().lower())] = -0.12

    for title in target_titles or []:
        normalized = title.strip().lower()
        if normalized:
            weights[facet_key("job_family", normalized)] = 0.06

    return weights
