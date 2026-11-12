"""Serialize / restore PreferenceState fields for persistence in preference_weights.weights."""

from __future__ import annotations

from typing import Any

from core.types import PreferenceState, SessionState, UserProfile


def preference_state_from_stored(profile: UserProfile, stored: dict[str, Any]) -> PreferenceState:
    """Rebuild PreferenceState including taste accumulators and session guards."""
    session_data = stored.get("session") or {}
    employer_counts = dict(session_data.get("employer_counts_today") or {})
    return PreferenceState(
        profile=profile,
        session=SessionState(
            same_direction_streak=int(session_data.get("same_direction_streak") or 0),
            last_direction=session_data.get("last_direction"),
            employer_counts_today=employer_counts,
        ),
        taste_positive_sum=[float(v) for v in stored.get("taste_positive_sum") or []],
        taste_positive_weight=float(stored.get("taste_positive_weight") or 0.0),
        taste_negative_sum=[float(v) for v in stored.get("taste_negative_sum") or []],
        taste_negative_weight=float(stored.get("taste_negative_weight") or 0.0),
    )


def serialize_preference_state(state: PreferenceState) -> dict[str, Any]:
    """Extract persistable fields from PreferenceState (excluding profile scalars)."""
    return {
        "taste_positive_sum": state.taste_positive_sum,
        "taste_positive_weight": state.taste_positive_weight,
        "taste_negative_sum": state.taste_negative_sum,
        "taste_negative_weight": state.taste_negative_weight,
        "session": {
            "same_direction_streak": state.session.same_direction_streak,
            "last_direction": state.session.last_direction,
            "employer_counts_today": dict(state.session.employer_counts_today),
        },
    }
