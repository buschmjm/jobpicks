"""Why/caution match explanations with template fallback."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MatchExplanation:
    why: list[str] = field(default_factory=list)
    caution: list[str] = field(default_factory=list)
    source: str = "template"

    def as_dict(self) -> dict[str, list[str] | str]:
        return {"why": self.why, "caution": self.caution, "source": self.source}


def _format_currency(amount: int | float | None) -> str | None:
    if amount is None:
        return None
    return f"${int(amount):,}"


def template_explanation(
    *,
    user_profile: dict[str, Any],
    job: dict[str, Any],
    score_features: dict[str, Any] | None = None,
) -> MatchExplanation:
    """Deterministic why/caution bullets from structured features."""
    if score_features and any(k in score_features for k in ("semantic", "skill", "comp", "level", "title")):
        return match_explanation_from_components(score_features)
    why: list[str] = []
    caution: list[str] = []
    features = score_features or {}

    user_skills = _skill_set(user_profile)
    job_skills = _skill_set(job)
    overlap = sorted(user_skills & job_skills)
    if overlap:
        shown = ", ".join(overlap[:4])
        why.append(f"Strong overlap on {shown}")

    user_target = _salary_target(user_profile)
    job_min = job.get("salary_min") or job.get("salary", {}).get("min")
    if user_target and job_min:
        if job_min >= user_target:
            why.append(f"Meets your {_format_currency(user_target)}+ salary target")
        else:
            caution.append(
                f"Listed salary may be below your {_format_currency(user_target)} target"
            )

    user_remote = _remote_preference(user_profile)
    job_remote = job.get("work_arrangement") or job.get("remote")
    if user_remote and job_remote:
        if _remote_matches(user_remote, job_remote):
            why.append("Work arrangement matches your preference")
        else:
            caution.append("Work arrangement may not match your preference")

    user_level = _seniority(user_profile)
    job_level = job.get("seniority_level")
    if user_level and job_level:
        if user_level == job_level:
            why.append(f"Seniority level ({job_level}) aligns with your experience")
        elif _level_gap(user_level, job_level) > 0:
            caution.append(f"Role expects {job_level} level — you appear {user_level}")

    missing = sorted(job_skills - user_skills)
    if missing and len(missing) <= 3:
        caution.append(f"Wants {', '.join(missing[:3])} — not highlighted on your profile")
    elif missing:
        caution.append(f"Wants skills you may lack (e.g. {', '.join(missing[:2])})")

    semantic = features.get("semantic_score")
    if semantic is not None and semantic >= 0.75 and not why:
        why.append("Strong semantic fit with your recent interests")

    if not why:
        why.append("Passes your hard constraints and ranks in your top matches")
    if len(why) > 4:
        why = why[:4]
    if len(caution) > 2:
        caution = caution[:2]

    return MatchExplanation(why=why, caution=caution, source="template")


def match_explanation_from_components(components: dict[str, Any]) -> MatchExplanation:
    """Template-rendered match explanation from queue-build score components (zero LLM)."""
    why: list[str] = []
    caution: list[str] = []

    labels = (
        ("semantic", "Profile fit"),
        ("skill", "Skills overlap"),
        ("title", "Title alignment"),
        ("level", "Seniority fit"),
        ("comp", "Compensation fit"),
        ("geo", "Location fit"),
    )
    ranked = sorted(
        ((key, float(components.get(key, 0.0))) for key, _ in labels),
        key=lambda item: item[1],
        reverse=True,
    )
    for key, value in ranked[:4]:
        if value >= 0.7:
            label = next(lbl for k, lbl in labels if k == key)
            why.append(f"Strong {label.lower()}")
        elif value < 0.35 and key in {"level", "comp"}:
            label = next(lbl for k, lbl in labels if k == key)
            caution.append(f"Weaker {label.lower()}")

    facets = float(components.get("facets", 0.0) or 0.0)
    qual = float(components.get("qual_penalty", 0.0) or 0.0)
    if facets > 0.05:
        why.append("Matches learned preferences from your swipe history")
    if qual > 0.1:
        caution.append("Some qualification gaps flagged from past feedback")

    if not why:
        why.append("Passes your hard constraints and ranks in your top matches")
    return MatchExplanation(why=why[:4], caution=caution[:2], source="template")


def explain_match(
    *,
    user_profile: dict[str, Any],
    job: dict[str, Any],
    score_features: dict[str, Any] | None = None,
) -> MatchExplanation:
    """Generate why/caution bullets from score components only (no LLM)."""
    if score_features:
        return match_explanation_from_components(score_features)
    return template_explanation(
        user_profile=user_profile,
        job=job,
        score_features=score_features,
    )


def _bullet_list(raw: Any, *, min_items: int, max_items: int) -> list[str]:
    if not isinstance(raw, list):
        return []
    bullets = [str(item).strip() for item in raw if str(item).strip()]
    if len(bullets) < min_items:
        return bullets
    return bullets[:max_items]


def _skill_set(profile: dict[str, Any]) -> set[str]:
    skills: set[str] = set()
    raw = profile.get("skills") or profile.get("required_skills") or []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and "value" in item:
                skills.add(str(item["value"]).lower())
            else:
                skills.add(str(item).lower())
    required = profile.get("required_skills") or []
    if isinstance(required, list):
        skills.update(str(item).lower() for item in required)
    return skills


def _salary_target(profile: dict[str, Any]) -> int | None:
    constraints = profile.get("hard_constraints") or profile.get("constraints") or {}
    if isinstance(constraints, dict):
        target = constraints.get("min_salary") or constraints.get("salary_min")
        if target is not None:
            return int(target)
    target_fact = profile.get("target_salary") or profile.get("min_salary")
    if isinstance(target_fact, dict):
        value = target_fact.get("value")
        return int(value) if value is not None else None
    if target_fact is not None:
        return int(target_fact)
    return None


def _remote_preference(profile: dict[str, Any]) -> str | None:
    constraints = profile.get("hard_constraints") or profile.get("constraints") or {}
    if isinstance(constraints, dict):
        pref = constraints.get("remote_preference") or constraints.get("work_mode")
        if pref:
            return str(pref).lower()
    return None


def _remote_matches(preference: str, job_mode: Any) -> bool:
    job = str(job_mode).lower()
    if preference in {"remote", "any"}:
        return job in {"remote", "hybrid", "true", "yes"}
    if preference == "hybrid":
        return job in {"hybrid", "remote", "onsite"}
    return job in {preference, "hybrid", "onsite"}


def _seniority(profile: dict[str, Any]) -> str | None:
    level = profile.get("seniority_level") or profile.get("level")
    if isinstance(level, dict):
        level = level.get("value")
    return str(level).lower() if level else None


_LEVEL_ORDER = ["intern", "junior", "mid", "senior", "staff", "principal", "lead"]


def _level_gap(user_level: str, job_level: str) -> int:
    user = _LEVEL_ORDER.index(user_level) if user_level in _LEVEL_ORDER else 2
    job = _LEVEL_ORDER.index(job_level) if job_level in _LEVEL_ORDER else 2
    return job - user
