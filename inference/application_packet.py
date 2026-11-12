"""Application packet inference — fit verdict and rationale."""

from __future__ import annotations

import json
import logging
from typing import Any

from inference.client import InferenceUnavailableError, get_client
from inference.extraction import ExtractionError, _chat_json
from inference.prompts import load_prompt

logger = logging.getLogger(__name__)


def _default_fit(job: dict[str, Any]) -> dict[str, Any]:
    title = str(job.get("title") or "this role").strip()
    company = str(job.get("company") or "the company").strip()
    return {
        "fit_verdict": "lean_apply",
        "fit_rationale": [
            f"Profile appears reasonably aligned with {title} at {company}.",
            "Review the job description and confirm fit before applying.",
        ],
        "source": "template",
    }


def propose_application_packet(
    *,
    profile: dict[str, Any],
    identity: dict[str, Any],
    job: dict[str, Any],
) -> dict[str, Any]:
    """Return fit verdict and rationale for a job application."""
    fallback = _default_fit(job)

    loaded = load_prompt("application_packet")
    payload = {
        "profile": profile,
        "identity": identity,
        "job": job,
    }
    user_content = json.dumps(payload, ensure_ascii=False)
    try:
        client = get_client()
        data = _chat_json(client, loaded, user_content)
        rationale = [
            str(item).strip()
            for item in (data.get("fit_rationale") or [])
            if str(item).strip()
        ][:6]
        if not rationale:
            rationale = list(fallback["fit_rationale"])
        return {
            "fit_verdict": str(data.get("fit_verdict") or "lean_apply"),
            "fit_rationale": rationale,
            "source": "llm",
        }
    except (InferenceUnavailableError, ExtractionError, Exception) as exc:
        logger.warning("application packet LLM unavailable, using template: %s", exc)
        return fallback
