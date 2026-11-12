"""Saved application answer vault helpers."""

from __future__ import annotations

import re
from typing import Any

AUTO_VAULT_KEYS = frozenset(
    {
        "work_authorization",
        "sponsorship",
        "salary_expectation",
    }
)

_KEY_RE = re.compile(r"[^a-z0-9]+")


def normalize_question_key(text: str) -> str:
    """Slugify question text or key for vault deduplication."""
    raw = (text or "").strip().lower()
    if not raw:
        return ""
    raw = raw.replace("-", "_")
    slug = _KEY_RE.sub("_", raw).strip("_")
    return slug[:128]


def vault_map(entries: list[Any]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for row in entries:
        raw_key = getattr(row, "question_key", None)
        if raw_key is None and isinstance(row, dict):
            raw_key = row.get("question_key")
        key = str(raw_key or "")
        if not key:
            continue
        answer = str(getattr(row, "answer", None) or (row.get("answer") if isinstance(row, dict) else "") or "").strip()
        if not answer:
            continue
        question_text = str(
            getattr(row, "question_text", None)
            or (row.get("question_text") if isinstance(row, dict) else "")
            or key.replace("_", " ").title()
        )
        out[key] = {"question_text": question_text, "answer": answer}
    return out


def merge_vault_into_answers(
    answers: list[dict[str, Any]],
    vault: dict[str, dict[str, str]],
    *,
    preconfirm: bool = True,
) -> list[dict[str, Any]]:
    """Overlay vault values onto packet answers by question key."""
    if not vault:
        return answers

    merged: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in answers:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        if not key:
            continue
        seen.add(key)
        row = dict(item)
        hit = vault.get(key)
        if hit:
            row["suggested_answer"] = hit["answer"]
            row["question_text"] = hit.get("question_text") or row.get("question_text") or key
            row["source"] = "vault"
            if preconfirm:
                row["status"] = "confirmed"
                row["final_answer"] = hit["answer"]
        merged.append(row)

    for key, hit in vault.items():
        if key in seen:
            continue
        merged.append(
            {
                "key": key,
                "question_text": hit.get("question_text") or key.replace("_", " ").title(),
                "suggested_answer": hit["answer"],
                "source": "vault",
                "status": "confirmed" if preconfirm else "pending",
                "final_answer": hit["answer"] if preconfirm else None,
                "save_to_vault": False,
            }
        )

    return merged[:12]
