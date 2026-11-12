"""Load ScoringConfig from DB rows (handles nested migration seed shapes)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.models import ScoringConfig as ScoringConfigRow
from core.types import ScoringConfig

_KEY_ALIASES: dict[str, str] = {
    "feedback_half_life_days": "signal_half_life_days",
    "daily_queue_topup_cap": "daily_topup_cap",
}

_NESTED_EXTRACT: dict[str, str] = {
    "feedback_half_life_days": "days",
    "cold_start_right_swipe_threshold": "count",
    "daily_queue_topup_cap": "count",
    "backfill_deck_cap": "count",
    "backfill_max_jobs_per_employer": "count",
    "explore_slot_ratio": "ratio",
}


def _flatten_row(key: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {_KEY_ALIASES.get(key, key): value}
    field = _KEY_ALIASES.get(key, key)
    if key in _NESTED_EXTRACT and _NESTED_EXTRACT[key] in value:
        return {field: value[_NESTED_EXTRACT[key]]}
    if key == "mindless_swipe_guard":
        out: dict[str, Any] = {}
        if "streak_threshold" in value:
            out["mindless_streak_threshold"] = value["streak_threshold"]
        if "min_dwell_seconds" in value:
            out["min_dwell_seconds"] = value["min_dwell_seconds"]
        return out
    if key == "score_weights":
        return dict(value)
    return {field: value}


def scoring_config_from_db_rows(rows: list[ScoringConfigRow]) -> ScoringConfig:
    """Load ScoringConfig dataclass from scoring_config key/value rows."""
    merged: dict[str, Any] = {}
    for row in rows:
        merged.update(_flatten_row(row.key, row.value))

    kwargs: dict[str, Any] = {}
    for field_name in ScoringConfig.__dataclass_fields__:
        if field_name in merged:
            kwargs[field_name] = merged[field_name]
    return ScoringConfig(**kwargs)


def load_scoring_config(session: Session) -> ScoringConfig:
    rows = session.scalars(select(ScoringConfigRow)).all()
    if not rows:
        return ScoringConfig()
    return scoring_config_from_db_rows(list(rows))
