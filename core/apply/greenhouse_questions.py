"""Fetch Greenhouse screening questions for packet enrichment."""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from core.apply.ats_detect import detect_ats

logger = logging.getLogger(__name__)

_GH_API = "https://boards-api.greenhouse.io/v1/boards"


def _slugify_key(label: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", (label or "").lower()).strip("_")
    return cleaned[:128] or "screening_question"


def fetch_greenhouse_questions(
    *,
    apply_url: str,
    ats_metadata: dict[str, Any] | None = None,
    timeout: float = 10.0,
) -> list[dict[str, Any]]:
    """Return packet-style answer drafts from Greenhouse public job API."""
    ats_type, metadata = detect_ats(apply_url)
    if ats_type != "greenhouse":
        return []

    merged = {**(ats_metadata or {}), **metadata}
    board_token = str(merged.get("board_token") or "").strip()
    posting_id = str(merged.get("posting_id") or "").strip()
    if not board_token or not posting_id:
        return []

    url = f"{_GH_API}/{board_token}/jobs/{posting_id}"
    try:
        response = httpx.get(url, timeout=timeout, headers={"Accept": "application/json"})
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        logger.debug("greenhouse questions fetch failed %s: %s", url, exc)
        return []

    questions = payload.get("questions") or []
    answers: list[dict[str, Any]] = []
    for item in questions:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        if not label:
            continue
        required = bool(item.get("required"))
        key = _slugify_key(label)
        answers.append(
            {
                "key": key,
                "question_text": label[:500],
                "suggested_answer": "",
                "source": "ats",
                "status": "pending",
                "final_answer": None,
                "save_to_vault": False,
                "required": required,
            }
        )
        if len(answers) >= 12:
            break
    return answers


def merge_greenhouse_question_stubs(
    existing: list[dict[str, Any]],
    stubs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Add GH question stubs for keys not already present in packet answers."""
    if not stubs:
        return existing
    by_key = {str(item.get("key")): dict(item) for item in existing if isinstance(item, dict)}
    for stub in stubs:
        key = str(stub.get("key") or "")
        if not key or key in by_key:
            continue
        by_key[key] = stub
    return list(by_key.values())[:12]
