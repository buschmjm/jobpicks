"""Default and user-customizable application workflow steps."""

from __future__ import annotations

import uuid
from typing import Any

DEFAULT_APPLICATION_STEPS: list[dict[str, Any]] = [
    {
        "id": "review",
        "label": "Review application packet",
        "done": False,
        "order": 0,
    },
    {
        "id": "customize",
        "label": "Customize resume & cover letter",
        "done": False,
        "order": 1,
    },
    {
        "id": "submit",
        "label": "Submit on employer site",
        "done": False,
        "order": 2,
    },
    {
        "id": "follow_up",
        "label": "Follow up / track response",
        "done": False,
        "order": 3,
    },
]


def clone_default_steps() -> list[dict[str, Any]]:
    return [dict(step) for step in DEFAULT_APPLICATION_STEPS]


def steps_from_template(template: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not template:
        return clone_default_steps()
    return normalize_steps(template, allow_empty=False)


def normalize_steps(
    raw_steps: list[dict[str, Any]],
    *,
    allow_empty: bool = True,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_steps):
        label = str(raw.get("label", "")).strip()
        if not label:
            continue
        step_id = str(raw.get("id") or uuid.uuid4())
        normalized.append(
            {
                "id": step_id,
                "label": label[:200],
                "done": bool(raw.get("done")),
                "order": int(raw.get("order", index)),
            }
        )
    normalized.sort(key=lambda step: step["order"])
    for index, step in enumerate(normalized):
        step["order"] = index
    if not normalized and not allow_empty:
        return clone_default_steps()
    return normalized


def progress_summary(steps: list[dict[str, Any]]) -> tuple[int, int]:
    total = len(steps)
    done = sum(1 for step in steps if step.get("done"))
    return done, total
