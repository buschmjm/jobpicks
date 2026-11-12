"""Career assistant inference: job title suggestions."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Literal

from inference.client import InferenceClient, InferenceUnavailableError, get_client
from inference.extraction import ExtractionError, _chat_json
from inference.prompts import LoadedPrompt, load_prompt

logger = logging.getLogger(__name__)

TitleTier = Literal["qualified", "adjacent"]
SuggestionSource = Literal["llm", "template"]


@dataclass(frozen=True)
class TitleSuggestionResult:
    title: str
    tier: TitleTier
    reason: str


@dataclass(frozen=True)
class TitleSuggestionsOutput:
    suggestions: list[TitleSuggestionResult]
    source: SuggestionSource


def _normalize_title(title: str) -> str:
    return " ".join(title.strip().split())


def _dedupe_suggestions(items: list[TitleSuggestionResult]) -> list[TitleSuggestionResult]:
    seen: set[str] = set()
    out: list[TitleSuggestionResult] = []
    for item in items:
        key = item.title.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _parse_llm_suggestions(data: dict[str, Any]) -> list[TitleSuggestionResult]:
    rows = data.get("suggestions") or []
    results: list[TitleSuggestionResult] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = _normalize_title(str(row.get("title") or ""))
        tier = row.get("tier")
        reason = str(row.get("reason") or "").strip()
        if not title or tier not in {"qualified", "adjacent"} or not reason:
            continue
        results.append(
            TitleSuggestionResult(title=title, tier=tier, reason=reason[:160])
        )
    return _dedupe_suggestions(results)


def _has_leadership_highlights(snapshot: dict[str, Any]) -> bool:
    from core.career.profile_snapshot import snapshot_roles

    keywords = ("lead", "managed", "mentor", "supervis", "team", "direct report")
    for exp in snapshot_roles(snapshot):
        blob = " ".join(
            [str(exp.get("job_title") or "")]
            + [str(h) for h in (exp.get("highlights") or []) if h]
        ).lower()
        if any(word in blob for word in keywords):
            return True
    return False


def template_title_suggestions(snapshot: dict[str, Any]) -> list[TitleSuggestionResult]:
    """Deterministic fallback when LLM is unavailable."""
    from core.career.profile_snapshot import snapshot_roles, snapshot_total_years

    suggestions: list[TitleSuggestionResult] = []
    seen_titles: set[str] = set()

    def add(title: str, tier: TitleTier, reason: str) -> None:
        normalized = _normalize_title(title)
        if not normalized:
            return
        key = normalized.lower()
        if key in seen_titles:
            return
        seen_titles.add(key)
        suggestions.append(TitleSuggestionResult(title=normalized, tier=tier, reason=reason))

    roles = snapshot_roles(snapshot)
    years = snapshot_total_years(snapshot)
    overview = snapshot.get("profile_overview")
    if not isinstance(overview, dict):
        overview = {}
    senior = str(overview.get("seniority_level") or snapshot.get("seniority_level") or "").lower()
    is_senior = senior in {"senior", "staff", "principal", "lead"} or (
        isinstance(years, (int, float)) and years >= 5
    )

    for exp in roles:
        title = str(exp.get("job_title") or "").strip()
        if not title:
            continue
        add(
            title,
            "qualified",
            "Matches a role you've already held in your work history.",
        )
        if is_senior and not title.lower().startswith("senior"):
            add(
                f"Senior {title}",
                "qualified",
                "Natural seniority step based on your experience level.",
            )

    if roles:
        base_title = str(roles[0].get("job_title") or "").strip()
        if base_title:
            if _has_leadership_highlights(snapshot):
                add(
                    f"{base_title} Lead",
                    "adjacent",
                    "Your highlights suggest leadership experience that could translate to a lead role.",
                )
            add(
                f"{base_title} Manager",
                "adjacent",
                "A people-management path adjacent to your current job family.",
            )

    skills = snapshot.get("skills") or []
    if skills and not suggestions:
        skill_sample = ", ".join(str(s) for s in skills[:3])
        add(
            "Specialist",
            "adjacent",
            f"Consider titles that emphasize your skills ({skill_sample}).",
        )

    if not suggestions:
        add(
            "Job Seeker",
            "qualified",
            "Add work history or skills to get more tailored title suggestions.",
        )

    return _dedupe_suggestions(suggestions)[:10]


def suggest_job_titles_llm(
    snapshot: dict[str, Any],
    *,
    client: InferenceClient | None = None,
    prompt: LoadedPrompt | None = None,
    max_attempts: int = 2,
) -> list[TitleSuggestionResult]:
    llm = client or get_client()
    loaded = prompt or load_prompt("title_suggest")
    user_content = json.dumps(snapshot, ensure_ascii=False)
    data = _chat_json(llm, loaded, user_content, max_attempts=max_attempts)
    results = _parse_llm_suggestions(data)
    if len(results) < 3:
        raise ExtractionError("Too few title suggestions from LLM")
    return results


def suggest_job_titles(
    snapshot: dict[str, Any],
    *,
    client: InferenceClient | None = None,
) -> TitleSuggestionsOutput:
    """Return title suggestions; fall back to template on inference failure."""
    try:
        suggestions = suggest_job_titles_llm(snapshot, client=client)
        return TitleSuggestionsOutput(suggestions=suggestions, source="llm")
    except (InferenceUnavailableError, ExtractionError, ValueError) as exc:
        logger.warning("title suggestions LLM unavailable, using template: %s", exc)
        return TitleSuggestionsOutput(
            suggestions=template_title_suggestions(snapshot),
            source="template",
        )
