"""JSON research planner for the career advisor."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from inference.client import InferenceClient, InferenceUnavailableError, get_client
from inference.extraction import ExtractionError, _chat_json
from inference.prompts import LoadedPrompt, load_prompt
from inference.research.tools import ResearchBundle

logger = logging.getLogger(__name__)

_FORCE_RESEARCH = re.compile(
    r"\b("
    r"salary|salaries|comp|compensation|pay|market|hiring|outlook|demand|"
    r"worth applying|should i apply|lean apply|lean skip|"
    r"job description|fit assessment|discuss this role|"
    r"hiring in|roles in|jobs in|cost of living|going rate|band|bands"
    r")\b",
    re.I,
)


def should_force_research(user_message: str) -> bool:
    """Heuristic: market / pay / apply-fit questions should always research."""
    return bool(_FORCE_RESEARCH.search(user_message or ""))


def _location_hint(snapshot: dict[str, Any]) -> str | None:
    prefs = snapshot.get("preferences") if isinstance(snapshot, dict) else None
    if not isinstance(prefs, dict):
        return None
    locs = prefs.get("locations") or []
    for loc in locs:
        if isinstance(loc, dict):
            name = loc.get("name") or loc.get("formatted_name")
            if name:
                return str(name)[:120]
        elif loc:
            return str(loc)[:120]
    return None


def _title_hints(snapshot: dict[str, Any]) -> list[str]:
    prefs = snapshot.get("preferences") if isinstance(snapshot, dict) else None
    titles: list[str] = []
    if isinstance(prefs, dict):
        for t in prefs.get("target_titles") or []:
            if t:
                titles.append(str(t)[:80])
    return titles[:5]


def _fallback_plan(snapshot: dict[str, Any], user_message: str) -> dict[str, Any]:
    titles = _title_hints(snapshot)
    location = _location_hint(snapshot) or "United States"
    title = titles[0] if titles else "software engineer"
    searches = [
        f"{title} salary {location} 2025 2026",
        f"{title} hiring demand {location}",
    ]
    if "apply" in user_message.lower() or "job description" in user_message.lower():
        searches.append(f"{title} requirements typical {location}")
    return {
        "need_research": True,
        "rationale": "Heuristic market/fit research",
        "searches": searches[:3],
        "fetches": [],
        "corpus_query": f"{title} {location}",
    }


def plan_research(
    *,
    snapshot: dict[str, Any],
    user_message: str,
    client: InferenceClient | None = None,
    prompt: LoadedPrompt | None = None,
) -> dict[str, Any]:
    """Return a validated research plan dict."""
    force = should_force_research(user_message)
    llm = client or get_client()
    loaded = prompt or load_prompt("career_research_plan")
    titles = _title_hints(snapshot)
    location = _location_hint(snapshot)
    payload = {
        "message": user_message.strip()[:4000],
        "target_titles": titles,
        "location": location,
        "force_research": force,
    }
    try:
        data = _chat_json(
            llm,
            loaded,
            json.dumps(payload, ensure_ascii=False),
            max_attempts=2,
        )
    except (InferenceUnavailableError, ExtractionError, ValueError) as exc:
        logger.warning("research planner unavailable, using heuristic: %s", exc)
        return _fallback_plan(snapshot, user_message) if force else {
            "need_research": False,
            "rationale": "Planner unavailable",
            "searches": [],
            "fetches": [],
            "corpus_query": "",
        }

    need = bool(data.get("need_research"))
    if force:
        need = True
    searches = [str(s).strip()[:240] for s in (data.get("searches") or []) if str(s).strip()]
    fetches = [str(u).strip()[:2048] for u in (data.get("fetches") or []) if str(u).strip()]
    corpus_query = str(data.get("corpus_query") or "").strip()[:240]

    if need and not searches and not corpus_query:
        return _fallback_plan(snapshot, user_message)

    return {
        "need_research": need,
        "rationale": str(data.get("rationale") or "")[:240],
        "searches": searches[:3],
        "fetches": fetches[:2],
        "corpus_query": corpus_query,
    }


def empty_bundle(*, detail: str = "") -> ResearchBundle:
    return ResearchBundle(failed=True, detail=detail)
