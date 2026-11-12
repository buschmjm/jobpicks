"""Resume tailoring inference — select catalog items for a job."""

from __future__ import annotations

import logging
from typing import Any

from core.resume.document import heuristic_tailor_selection

from inference.client import InferenceUnavailableError, get_client
from inference.extraction import ExtractionError, _chat_json
from inference.prompts import load_prompt

logger = logging.getLogger(__name__)


def propose_resume_tailor(
    *,
    catalog: dict[str, Any],
    job: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    """Return (selection dict, source) where source is llm|template."""
    job_blob = " ".join(
        str(job.get(k) or "")
        for k in ("title", "company", "description", "why", "caution")
    )
    fallback = heuristic_tailor_selection(catalog, job_blob)

    loaded = load_prompt("resume_tailor")
    payload = {
        "job": job,
        "catalog": {
            "summary_paragraphs": catalog.get("summary_paragraphs") or [],
            "roles": [
                {
                    "experience_id": role.get("experience_id"),
                    "title": role.get("title"),
                    "company_name": role.get("company_name"),
                    "highlights": [
                        {"index": idx, "text": (h.get("text") if isinstance(h, dict) else str(h))}
                        for idx, h in enumerate(role.get("highlights") or [])
                    ],
                }
                for role in (catalog.get("roles") or [])
                if isinstance(role, dict)
            ],
            "skill_names": [
                (item.get("text") if isinstance(item, dict) else str(item))
                for group in (catalog.get("skill_groups") or [])
                for item in (group.get("items") or [])
            ],
            "education": catalog.get("education") or [],
        },
    }
    messages = [
        {"role": "system", "content": loaded.system_message},
        {"role": "user", "content": __import__("json").dumps(payload, ensure_ascii=False)},
    ]
    try:
        client = get_client()
        data = _chat_json(client, loaded, messages[1]["content"])
        selection = _normalize_selection(data, catalog)
        return selection, "llm"
    except (InferenceUnavailableError, ExtractionError, Exception) as exc:
        logger.warning("resume tailor LLM unavailable, using heuristic: %s", exc)
        return fallback, "template"


def _normalize_selection(data: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    known_skills = {
        str(item.get("text") if isinstance(item, dict) else item).strip().lower()
        for group in (catalog.get("skill_groups") or [])
        for item in (group.get("items") or [])
    }
    skill_names = []
    for name in data.get("skill_names") or []:
        clean = str(name).strip()
        if clean and clean.lower() in known_skills:
            skill_names.append(clean)

    role_ids = {str(r.get("experience_id")) for r in (catalog.get("roles") or []) if isinstance(r, dict)}
    role_selections = []
    for sel in data.get("role_selections") or []:
        if not isinstance(sel, dict):
            continue
        rid = str(sel.get("experience_id") or "")
        if rid not in role_ids:
            continue
        indices = []
        for i in sel.get("highlight_indices") or []:
            try:
                indices.append(int(i))
            except (TypeError, ValueError):
                continue
        role_selections.append(
            {
                "experience_id": rid,
                "include": bool(sel.get("include", True)),
                "highlight_indices": indices[:8],
            }
        )

    edu_count = len(catalog.get("education") or [])
    education_indices = []
    for i in data.get("education_indices") or []:
        try:
            idx = int(i)
        except (TypeError, ValueError):
            continue
        if 0 <= idx < edu_count:
            education_indices.append(idx)

    paragraphs = [str(p).strip() for p in (data.get("summary_paragraphs") or []) if str(p).strip()]
    if not paragraphs:
        paragraphs = list(catalog.get("summary_paragraphs") or [])[:2]

    return {
        "rationale": str(data.get("rationale") or "").strip()
        or "Tailored selection from your saved experience.",
        "summary_paragraphs": paragraphs[:3],
        "role_selections": role_selections,
        "skill_names": skill_names[:30],
        "education_indices": education_indices or list(range(edu_count)),
    }
